"""Trial Agent — ClinicalTrials.gov via Zetaris."""
from agents.data_agent import run_data_agent
from agents.state import PipelineState


def trial_node(state: PipelineState) -> dict:
    return run_data_agent(state, agent="trial", index=0, source="trials",
                          provenance="ClinicalTrials.gov", findings_key="trial_findings")
