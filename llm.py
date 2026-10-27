"""LLM access: NVIDIA Nemotron first (with model-level fallback chain),
then GPT-4o-mini, then heuristic.

If a model is permanently dead (HTTP 401/403/404/410) it is added to `_dead`
and skipped on every subsequent call.  When the primary NVIDIA model fails,
the system walks NVIDIA_MODEL_FALLBACKS in order before giving up on NVIDIA.
Every call returns (None, "heuristic") when no model could answer, so agents
can degrade gracefully instead of crashing.
"""
import json
import logging
import re

import config

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
# Cache keyed by (model_id, temperature, max_tokens) → ChatOpenAI instance
_clients: dict[tuple[str, float, int | None], object] = {}
# Models that failed permanently — never tried again in this process
_dead: set[str] = set()
_PERMANENT_STATUS = {401, 403, 404, 410}


def _client(model_id: str, base_url: str | None, api_key: str,
            temperature: float, max_tokens: int | None):
    """Return a cached ChatOpenAI instance for the given model."""
    key = (model_id, temperature, max_tokens)
    if key in _clients:
        return _clients[key]
    from langchain_openai import ChatOpenAI

    kwargs: dict = dict(
        model=model_id,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )
    if base_url:
        kwargs["base_url"] = base_url
    # Nemotron models reason by default (~10x latency); disable unless asked
    if base_url and "nvidia" in base_url:
        kwargs["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": config.NVIDIA_THINKING}
        }
    client = ChatOpenAI(**kwargs)
    _clients[key] = client
    return client


def _call_model(model_id: str, base_url: str | None, api_key: str,
                system: str, user: str, temperature: float,
                max_tokens: int | None) -> str:
    """Invoke one model; raises on any error. Marks model dead on permanent errors."""
    if model_id in _dead:
        raise RuntimeError(f"Model {model_id!r} is permanently dead, skipping")
    client = _client(model_id, base_url, api_key, temperature, max_tokens)
    try:
        reply = client.invoke([("system", system), ("user", user)])
        return _THINK_RE.sub("", reply.content or "").strip()
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in _PERMANENT_STATUS:
            _dead.add(model_id)
            log.warning("Model %s permanently dead (HTTP %s): %s", model_id, status, exc)
        else:
            log.warning("Model %s transient error: %s", model_id, exc)
        raise


def _nvidia_models() -> list[str]:
    """Ordered list of NVIDIA models to try: env override first, then fallback chain."""
    primary = config.NVIDIA_MODEL
    chain = config.NVIDIA_MODEL_FALLBACKS

    # Start with the configured primary; append any fallbacks not already equal to it
    ordered = [primary] + [m for m in chain if m != primary]
    return [m for m in ordered if m not in _dead]


def _providers() -> list[str]:
    """Which top-level providers are available?"""
    if config.OFFLINE:
        return []
    providers = []
    if config.NVIDIA_API_KEY and _nvidia_models():
        providers.append("nvidia")
    if config.OPENAI_API_KEY and "openai" not in _dead:
        providers.append("openai")
    return providers


def available() -> bool:
    return bool(_providers())


def complete(system: str, user: str, temperature: float = 0.1,
             max_tokens: int | None = None) -> tuple[str | None, str]:
    """Return (text, model_used).  text is None if every provider failed."""
    if config.OFFLINE:
        return None, "heuristic"

    # --- NVIDIA: walk the fallback chain ---
    if config.NVIDIA_API_KEY:
        for model_id in _nvidia_models():
            try:
                text = _call_model(
                    model_id, config.NVIDIA_BASE_URL, config.NVIDIA_API_KEY,
                    system, user, temperature, max_tokens,
                )
                return text, model_id
            except Exception:
                # logged inside _call_model; try next
                continue

    # --- OpenAI fallback ---
    if config.OPENAI_API_KEY and "openai" not in _dead:
        try:
            text = _call_model(
                config.OPENAI_FALLBACK_MODEL, None, config.OPENAI_API_KEY,
                system, user, temperature, max_tokens,
            )
            return text, config.OPENAI_FALLBACK_MODEL
        except Exception:
            _dead.add("openai")
            log.warning("OpenAI fallback also failed; returning None")

    return None, "heuristic"


def extract_json(text: str | None):
    """Pull the first JSON object or array out of a model reply."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def complete_json(system: str, user: str, temperature: float = 0.1,
                  max_tokens: int | None = None) -> tuple[dict | list | None, str]:
    text, model = complete(system, user, temperature, max_tokens)
    return extract_json(text), model
