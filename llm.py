"""LLM access: NVIDIA Nemotron first, GPT-4o-mini fallback, heuristic fallback last.

Every call returns None when no model could answer, so agents can degrade
gracefully instead of crashing.
"""
import json
import logging
import re

import config

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_clients: dict[tuple[str, float], object] = {}
_dead: set[str] = set()   # providers that failed permanently (bad key, retired model)
_PERMANENT_STATUS = {401, 403, 404, 410}


def _client(provider: str, temperature: float):
    key = (provider, temperature)
    if key in _clients:
        return _clients[key]
    from langchain_openai import ChatOpenAI

    if provider == "nvidia":
        client = ChatOpenAI(
            model=config.NVIDIA_MODEL,
            api_key=config.NVIDIA_API_KEY,
            base_url=config.NVIDIA_BASE_URL,
            temperature=temperature,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=1,
        )
    else:
        client = ChatOpenAI(
            model=config.OPENAI_FALLBACK_MODEL,
            api_key=config.OPENAI_API_KEY,
            temperature=temperature,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=1,
        )
    _clients[key] = client
    return client


def _providers() -> list[str]:
    if config.OFFLINE:
        return []
    providers = []
    if config.NVIDIA_API_KEY:
        providers.append("nvidia")
    if config.OPENAI_API_KEY:
        providers.append("openai")
    return [p for p in providers if p not in _dead]


def available() -> bool:
    return bool(_providers())


def complete(system: str, user: str, temperature: float = 0.1) -> tuple[str | None, str]:
    """Return (text, model_used). text is None if every provider failed."""
    for provider in _providers():
        try:
            reply = _client(provider, temperature).invoke([("system", system), ("user", user)])
            text = _THINK_RE.sub("", reply.content or "").strip()
            model = config.NVIDIA_MODEL if provider == "nvidia" else config.OPENAI_FALLBACK_MODEL
            return text, model
        except Exception as exc:  # quota, network, auth — try the next provider
            if getattr(exc, "status_code", None) in _PERMANENT_STATUS:
                _dead.add(provider)
            log.warning("LLM provider %s failed: %s", provider, exc)
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


def complete_json(system: str, user: str, temperature: float = 0.1) -> tuple[dict | list | None, str]:
    text, model = complete(system, user, temperature)
    return extract_json(text), model
