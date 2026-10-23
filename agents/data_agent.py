"""Shared logic for the Trial, Literature and Outcomes agents."""
import time

from agents.common import trace_entry
from agents.state import PipelineState
from data.loader import get_source
from memory import HMem, WorldModel


def run_data_agent(state: PipelineState, *, agent: str, index: int, source: str,
                   provenance: str, findings_key: str, normalize: bool = False) -> dict:
    started = time.perf_counter()
    retry_count = state.get("retry_count", 0)
    retry_qs = state.get("retry_sub_questions") or []
    is_retry = retry_count > 0

    if is_retry:
        refined = retry_qs[index] if index < len(retry_qs) else ""
        if not refined:
            # Evaluator was happy with this source — keep previous findings.
            return {"trace": [trace_entry(agent, started, retry=retry_count,
                                          action="kept previous findings (no refined query)",
                                          results_count=len(state.get(findings_key, [])))]}
        sub_question = refined
    else:
        sub_question = state["sub_questions"][index]

    query_text = sub_question
    if normalize:
        query_text = WorldModel.session(state.get("world_model_id")).normalize(sub_question)

    query_fn, origin = get_source(source)
    findings = query_fn(query_text)

    hmem = HMem.session(state.get("memory_session_id"))
    if is_retry:
        hmem.clear_source(provenance)
    for row in findings:
        hmem.write(row, level="episodic", provenance={"source": provenance, "agent": agent},
                   confidence=1.0)

    return {
        findings_key: findings,
        "trace": [trace_entry(
            agent, started, retry=retry_count, data_origin=origin, sub_question=sub_question,
            query_sent=query_text, results_count=len(findings),
            result_ids=[r.get("nct_id") or r.get("pmid") or r.get("source_dataset") for r in findings],
        )],
    }
