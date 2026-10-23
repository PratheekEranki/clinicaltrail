"""Evaluator / Critic Agent — reads all findings from H-MEM, flags contradictions
between sources, and decides whether to synthesise or retry with refined queries."""
import time

import config
import llm
from agents.common import fmt_literature, fmt_outcomes, fmt_trials, trace_entry
from agents.state import PipelineState
from memory import HMem

SYSTEM = """You are the critic agent of a clinical evidence system. You receive findings
from three sources: ClinicalTrials.gov, PubMed, and a population outcomes dataset.
1. Identify contradictions between sources. Be skeptical: beyond opposite conclusions, a
   contradiction also includes a large gap in effect size (e.g. a trial's relative risk
   reduction vs a much smaller real-world difference), a subgroup where the effect weakens
   or reverses, or safety signals that undercut a claimed benefit. Rate severity: "low"
   (nuance/minor), "medium" (meaningful disagreement that changes how the answer should be
   qualified), "high" (directly opposite conclusions). Cite IDs (NCT IDs, PMIDs, dataset
   names) in claims. Return [] only if the sources genuinely agree.
2. Decide "retry" ONLY if a source returned nothing or clearly off-topic results AND a
   better-targeted query would likely help; otherwise "synthesise".
3. If retrying, give refined sub-questions as a list of 3 strings
   [trials, literature, outcomes]; use "" for any source that does not need re-querying.
Respond with ONLY a JSON object:
{"contradictions": [{"claim_a": "", "source_a": "", "claim_b": "", "source_b": "", "severity": "low|medium|high"}],
 "agreements": ["short statements where sources agree"],
 "decision": "synthesise|retry",
 "retry_sub_questions": ["", "", ""],
 "reasoning": "two sentences explaining the decision"}"""

SOURCES = {"trial_findings": "ClinicalTrials.gov", "literature_findings": "PubMed",
           "outcomes_findings": "outcomes_dataset"}
SEVERITIES = {"low", "medium", "high"}


def _from_memory(state: PipelineState) -> dict[str, list[dict]]:
    """Prefer H-MEM (the shared store); fall back to state if the session is gone."""
    hmem = HMem.session(state.get("memory_session_id"))
    out = {}
    for key, source in SOURCES.items():
        recs = hmem.query(filters={"source": source})
        out[key] = [r["content"] for r in recs] if recs else list(state.get(key, []))
    return out


def _heuristic(state: PipelineState, findings: dict) -> dict:
    empty = [k for k, v in findings.items() if not v]
    can_retry = state.get("retry_count", 0) < config.MAX_RETRY_COUNT
    if empty and can_retry:
        q = state["query"].strip().rstrip("?")
        broad = [q if k in empty else "" for k in SOURCES]
        return {"contradictions": [], "agreements": [], "decision": "retry",
                "retry_sub_questions": broad,
                "reasoning": f"No results from {', '.join(SOURCES[k] for k in empty)}; retrying with a broader query."}
    return {"contradictions": [], "agreements": [], "decision": "synthesise", "retry_sub_questions": [],
            "reasoning": "LLM unavailable — no automated contradiction analysis; proceeding to synthesis."}


def _clean_contradictions(raw) -> list[dict]:
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        sev = str(c.get("severity", "medium")).lower()
        out.append({
            "claim_a": str(c.get("claim_a", "")), "source_a": str(c.get("source_a", "")),
            "claim_b": str(c.get("claim_b", "")), "source_b": str(c.get("source_b", "")),
            "severity": sev if sev in SEVERITIES else "medium",
        })
    return out


def evaluator_node(state: PipelineState) -> dict:
    started = time.perf_counter()
    findings = _from_memory(state)
    retry_count = state.get("retry_count", 0)

    prompt = (
        f"Research question: {state['query']}\n\n"
        f"## ClinicalTrials.gov\n{fmt_trials(findings['trial_findings'])}\n\n"
        f"## PubMed\n{fmt_literature(findings['literature_findings'])}\n\n"
        f"## Outcomes dataset\n{fmt_outcomes(findings['outcomes_findings'])}\n\n"
        f"Retries used so far: {retry_count} of {config.MAX_RETRY_COUNT}."
    )
    result, model = llm.complete_json(SYSTEM, prompt, temperature=0.1)
    if not isinstance(result, dict):
        result, model = _heuristic(state, findings), "heuristic"

    contradictions = _clean_contradictions(result.get("contradictions"))
    decision = "retry" if str(result.get("decision", "")).lower() == "retry" else "synthesise"
    retry_qs = [str(q or "") for q in (result.get("retry_sub_questions") or [])][:3]
    retry_qs += [""] * (3 - len(retry_qs))

    forced = False
    if decision == "retry" and (retry_count >= config.MAX_RETRY_COUNT or not any(retry_qs)):
        decision, forced = "synthesise", True

    update = {
        "contradictions": contradictions,
        "decision": decision,
        "trace": [trace_entry(
            "evaluator", started, model=model, retry=retry_count,
            findings_counts={SOURCES[k]: len(v) for k, v in findings.items()},
            contradictions=len(contradictions),
            severities=[c["severity"] for c in contradictions],
            agreements=result.get("agreements", []),
            decision=decision, retry_guard_forced_synthesis=forced,
            retry_sub_questions=retry_qs if decision == "retry" else [],
            reasoning=result.get("reasoning", ""),
        )],
    }
    if decision == "retry":
        update["retry_sub_questions"] = retry_qs
        update["retry_count"] = retry_count + 1
    return update
