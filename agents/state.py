"""Shared LangGraph state — the contract between all agents."""
import operator
from typing import Annotated, TypedDict


class PipelineState(TypedDict, total=False):
    query: str
    sub_questions: list[str]          # [trials, literature, outcomes]
    entities: dict                    # conditions / drugs / populations / outcomes
    world_model_id: str
    memory_session_id: str
    trial_findings: list[dict]
    literature_findings: list[dict]
    outcomes_findings: list[dict]
    contradictions: list[dict]
    decision: str                     # "synthesise" | "retry"
    retry_sub_questions: list[str]
    retry_count: int
    last_result_ids: dict             # evaluator's view of the previous round, to detect no-op retries
    final_answer: str
    supporting_evidence: list[dict]
    contradicting_evidence: list[dict]
    confidence: float
    # The three data agents run in parallel and all append, so trace needs a reducer.
    trace: Annotated[list[dict], operator.add]
