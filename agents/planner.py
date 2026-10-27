"""Planner Agent — decomposes the query into 3 source-targeted sub-questions
and writes extracted entities to the Meterless World Model."""
import re
import time

import llm
from agents.common import trace_entry
from agents.state import PipelineState
from memory import HMem, WorldModel

SYSTEM = """You are the planning agent of a clinical evidence system.
Decompose the user's clinical research question into exactly three sub-questions:
1. "trials": targeted at ClinicalTrials.gov (registered trials, phases, primary endpoints)
2. "literature": targeted at PubMed (published research findings)
3. "outcomes": targeted at real-world population outcomes datasets (rates by condition, treatment, age group)
Also extract medical entities from the question.
Respond with ONLY a JSON object:
{"sub_questions": {"trials": "...", "literature": "...", "outcomes": "..."},
 "entities": {"conditions": [], "drugs": [], "populations": [], "outcomes": []},
 "reasoning": "one sentence on how you split the question"}"""

ENTITY_TYPES = {"conditions": "condition", "drugs": "drug",
                "populations": "population", "outcomes": "outcome"}


def _extract_keywords(query: str) -> str:
    """Extract a short keyword phrase (<=60 chars) suitable as a Zetaris/API search term.

    REST tables forward the sub-question as a URL/body parameter; a 200-char
    natural-language sentence triggers HTTP 400.  Drop stop-words, cap at 8 tokens.
    """
    STOP = {
        "a", "an", "the", "and", "or", "of", "on", "in", "for", "to", "is",
        "are", "was", "were", "what", "does", "do", "say", "about", "it",
        "that", "its", "with", "by", "from", "this", "these", "those", "have",
        "has", "been", "be", "at", "as", "not", "which", "how", "recent",
        "published", "trial", "evidence", "data", "confirm", "contradict",
        "patients", "patient",
    }
    words = re.sub(r"[^\w\s-]", " ", query.lower()).split()
    keywords = [w for w in words if w not in STOP and len(w) > 2][:8]
    phrase = " ".join(keywords) if keywords else query[:60].strip()
    return phrase[:60]


def _heuristic(query: str) -> dict:
    kw = _extract_keywords(query)
    return {
        "sub_questions": {
            "trials": kw,
            "literature": kw,
            "outcomes": kw,
        },
        "entities": {"conditions": [], "drugs": [], "populations": [], "outcomes": []},
        "reasoning": "LLM unavailable — used keyword extraction from the full query.",
    }


def planner_node(state: PipelineState) -> dict:
    started = time.perf_counter()
    query = state["query"]

    plan, model = llm.complete_json(SYSTEM, query, temperature=0.1, max_tokens=800)
    if not isinstance(plan, dict) or not isinstance(plan.get("sub_questions"), dict):
        plan, model = _heuristic(query), "heuristic"

    fallback = _heuristic(query)["sub_questions"]
    sq = plan["sub_questions"]
    sub_questions = [str(sq.get(k) or fallback[k]) for k in ("trials", "literature", "outcomes")]

    entities = plan.get("entities") if isinstance(plan.get("entities"), dict) else {}
    entities = {k: [str(x) for x in entities.get(k, []) if x] for k in ENTITY_TYPES}

    wm = WorldModel.session()
    for group, etype in ENTITY_TYPES.items():
        for name in entities[group]:
            wm.add_entity(name, etype)
    for cond in entities["conditions"]:
        for drug in entities["drugs"]:
            wm.assert_fact(drug, "treats", cond)
        for pop in entities["populations"]:
            wm.assert_fact(cond, "occurs_in", pop)
    hmem = HMem.session()

    return {
        "sub_questions": sub_questions,
        "entities": entities,
        "world_model_id": wm.session_id,
        "memory_session_id": hmem.session_id,
        "retry_count": 0,
        "retry_sub_questions": [],
        "trace": [trace_entry(
            "planner", started, model=model, sub_questions=sub_questions,
            entities=entities, world_model_entities=len(wm.all_entities()),
            reasoning=plan.get("reasoning", ""),
        )],
    }
