"""LangGraph state machine.

planner → (trial ∥ literature ∥ outcomes) → evaluator ─┬─ synthesise → synthesis → END
                     ▲                                  │
                     └──────────── retry (max N) ───────┘
"""
from langgraph.graph import END, START, StateGraph

import config
from agents.evaluator import evaluator_node
from agents.literature import literature_node
from agents.outcomes import outcomes_node
from agents.planner import planner_node
from agents.state import PipelineState
from agents.synthesis import synthesis_node
from agents.trial import trial_node

DATA_AGENTS = ["trial", "literature", "outcomes"]


def should_retry(state: PipelineState):
    # evaluator already enforces the guard; re-check so the graph can't loop forever
    # Use < (strict) so retry_count==MAX_RETRY_COUNT triggers synthesis, not another loop
    if state.get("decision") == "retry" and state.get("retry_count", 0) < config.MAX_RETRY_COUNT:
        return DATA_AGENTS
    return "synthesis"


def build_graph():
    g = StateGraph(PipelineState)
    g.add_node("planner", planner_node)
    g.add_node("trial", trial_node)
    g.add_node("literature", literature_node)
    g.add_node("outcomes", outcomes_node)
    g.add_node("evaluator", evaluator_node)
    g.add_node("synthesis", synthesis_node)

    g.add_edge(START, "planner")
    g.add_edge("planner", "trial")
    g.add_edge("planner", "literature")
    g.add_edge("planner", "outcomes")
    g.add_edge(DATA_AGENTS, "evaluator")   # join: waits for all three branches
    g.add_conditional_edges("evaluator", should_retry, DATA_AGENTS + ["synthesis"])
    g.add_edge("synthesis", END)
    return g.compile()


def run_pipeline(query: str) -> dict:
    graph = build_graph()
    return graph.invoke({"query": query, "trace": []},
                        {"recursion_limit": 10 + 5 * config.MAX_RETRY_COUNT})
