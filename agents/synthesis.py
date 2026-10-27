"""Synthesis Agent — steps through each evidence set with Meterless Markovian
(bounded carryover), then writes the final cited, confidence-scored answer."""
import time

import llm
from agents.common import (fmt_contradictions, fmt_literature, fmt_outcomes,
                           fmt_trials, trace_entry)
from agents.state import PipelineState
from memory import Markovian

GOAL = "Reconcile clinical evidence and produce traceable answer"

STEP_SYSTEM = """You maintain a running evidence summary for a clinical research question.
Given the current summary and a new evidence set, return an updated summary (max 250 words)
that keeps every source ID (NCT IDs, PMIDs, dataset names) tied to its claim. Plain text only."""

FINAL_SYSTEM = """You are the synthesis agent of a clinical evidence system. Using the evidence
summary and flagged contradictions, answer the research question for a non-technical clinical
researcher. Requirements:
- Cite specific NCT IDs and PMIDs (and dataset names) inline for every claim.
- Address each contradiction explicitly and explain which evidence you weight more and why.
- Do not invent sources or IDs that are not in the evidence.
- supporting_evidence / contradicting_evidence list ONLY records that actually address the
  research question. If the evidence is off-topic, leave both lists empty, say so in
  final_answer, and give a confidence near 0.
Respond with ONLY a JSON object:
{"final_answer": "3-6 sentence answer",
 "supporting_evidence": [{"source": "ClinicalTrials.gov|PubMed|outcomes_dataset", "id": "", "claim": ""}],
 "contradicting_evidence": [{"source": "", "id": "", "claim": ""}],
 "confidence": 0.0,
 "confidence_reasoning": "one sentence"}"""

SEVERITY_PENALTY = {"low": 0.03, "medium": 0.08, "high": 0.15}
HEURISTIC_CONFIDENCE_CAP = 0.5


def _evidence_score(state: PipelineState) -> tuple[float, dict]:
    """Transparent confidence baseline: source coverage minus a contradiction penalty."""
    coverage = sum(bool(state.get(k)) for k in
                   ("trial_findings", "literature_findings", "outcomes_findings")) / 3
    penalty = min(0.5, sum(SEVERITY_PENALTY.get(c.get("severity"), 0.08)
                           for c in state.get("contradictions", [])))
    score = round(max(0.0, coverage * (1 - penalty)), 2)
    return score, {"source_coverage": round(coverage, 2), "contradiction_penalty": round(penalty, 2)}


def _llm_step(goal: str, carryover: str, new_context: str) -> str:
    text, _ = llm.complete(
        STEP_SYSTEM,
        f"Goal: {goal}\n\nCurrent summary:\n{carryover or '(empty)'}\n\nNew evidence:\n{new_context}",
        temperature=0.2, max_tokens=600,
    )
    if text is None:
        raise RuntimeError("no LLM")  # Markovian falls back to concatenation
    return text


def _heuristic_answer(state: PipelineState) -> dict:
    trials, lit, outs = (state.get(k, []) for k in
                         ("trial_findings", "literature_findings", "outcomes_findings"))
    parts = []
    if trials:
        parts.append(f"{len(trials)} registered trial(s) were found ("
                     + ", ".join(t["nct_id"] for t in trials[:5]) + ").")
    if lit:
        parts.append(f"{len(lit)} published article(s) were found (PMIDs "
                     + ", ".join(a["pmid"] for a in lit[:5]) + ").")
    if outs:
        parts.append(f"{len(outs)} population outcome record(s) were found.")
    if state.get("contradictions"):
        parts.append(f"{len(state['contradictions'])} contradiction(s) were flagged between sources.")
    parts.append("Automated synthesis was unavailable (no LLM), so review the cited records directly.")
    support = ([{"source": "ClinicalTrials.gov", "id": t["nct_id"], "claim": t["primary_outcome"]} for t in trials]
               + [{"source": "PubMed", "id": a["pmid"], "claim": a["title"]} for a in lit]
               + [{"source": "outcomes_dataset", "id": o["source_dataset"],
                   "claim": f"{o['outcome_metric']} = {o['value']}"} for o in outs])
    return {"final_answer": " ".join(parts) if parts else "No evidence was found for this question.",
            "supporting_evidence": support, "contradicting_evidence": [],
            "confidence": None, "confidence_reasoning": "heuristic only"}


def _clean_evidence(raw) -> list[dict]:
    return [{"source": str(e.get("source", "")), "id": str(e.get("id", "")), "claim": str(e.get("claim", ""))}
            for e in (raw if isinstance(raw, list) else []) if isinstance(e, dict)]


def synthesis_node(state: PipelineState) -> dict:
    started = time.perf_counter()
    markov = Markovian(step_fn=_llm_step if llm.available() else None)
    markov.start_task(GOAL, constraints=["cite source IDs", "address contradictions"])

    # Two bounded steps (published evidence, then real-world data + contradictions)
    # keep Markovian carryover meaningful without an LLM call per source.
    for label, text in (
        ("trials+literature",
         f"[trials]\n{fmt_trials(state.get('trial_findings', []))}\n\n"
         f"[literature]\n{fmt_literature(state.get('literature_findings', []))}"),
        ("outcomes+contradictions",
         f"[outcomes]\n{fmt_outcomes(state.get('outcomes_findings', []))}\n\n"
         f"[contradictions]\n{fmt_contradictions(state.get('contradictions', []))}"),
    ):
        markov.next_step(None, text, label=label)

    prompt = (f"Research question: {state['query']}\n\n"
              f"Evidence summary:\n{markov.get_carryover()}\n\n"
              f"Flagged contradictions:\n{fmt_contradictions(state.get('contradictions', []))}")
    result, model = llm.complete_json(FINAL_SYSTEM, prompt, temperature=0.2, max_tokens=1500)
    if not isinstance(result, dict) or not result.get("final_answer"):
        result, model = _heuristic_answer(state), "heuristic"

    evidence_score, basis = _evidence_score(state)
    try:
        llm_conf = min(1.0, max(0.0, float(result.get("confidence"))))
    except (TypeError, ValueError):
        llm_conf = None
    if llm_conf is not None:
        # either signal alone can veto: rows that don't answer the question (llm low)
        # or sources that disagree / are missing (evidence low)
        confidence = round(min(llm_conf, evidence_score), 2)
    else:
        # no model reconciled the sources, so coverage alone can't justify high confidence
        confidence = min(evidence_score, HEURISTIC_CONFIDENCE_CAP)

    return {
        "final_answer": str(result["final_answer"]),
        "supporting_evidence": _clean_evidence(result.get("supporting_evidence")),
        "contradicting_evidence": _clean_evidence(result.get("contradicting_evidence")),
        "confidence": confidence,
        "trace": [trace_entry(
            "synthesis", started, model=model,
            markovian_task_id=markov.task_id, markovian_steps=markov.get_trace(),
            confidence=confidence, confidence_llm=llm_conf, confidence_evidence=evidence_score,
            confidence_basis=basis, confidence_reasoning=result.get("confidence_reasoning", ""),
        )],
    }
