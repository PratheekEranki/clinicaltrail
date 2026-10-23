"""Outcomes Agent — population outcomes Parquet/CSV via Zetaris."""
from agents.data_agent import run_data_agent
from agents.state import PipelineState


def outcomes_node(state: PipelineState) -> dict:
    return run_data_agent(state, agent="outcomes", index=2, source="outcomes",
                          provenance="outcomes_dataset", findings_key="outcomes_findings")
