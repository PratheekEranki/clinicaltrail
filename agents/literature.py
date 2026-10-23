"""Literature Agent — PubMed via Zetaris. Normalizes terminology through the
World Model first so "T2DM" and "type 2 diabetes" both match."""
from agents.data_agent import run_data_agent
from agents.state import PipelineState


def literature_node(state: PipelineState) -> dict:
    return run_data_agent(state, agent="literature", index=1, source="literature",
                          provenance="PubMed", findings_key="literature_findings",
                          normalize=True)
