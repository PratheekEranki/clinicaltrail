"""Offline pipeline tests — no LLM or network. Run: pytest -q"""
import os

os.environ["CLINICALTRAIL_OFFLINE"] = "true"
os.environ["USE_MOCK_DATA"] = "true"

import pytest  # noqa: E402

from data import loader, mock_sources  # noqa: E402
from data.loader import CONTRACT, _conform  # noqa: E402
from graph import run_pipeline  # noqa: E402
from llm import extract_json  # noqa: E402
from memory import HMem, Markovian, WorldModel  # noqa: E402


def test_full_pipeline_offline():
    result = run_pipeline("ACE inhibitors in elderly T2DM patients and cardiovascular outcomes?")
    assert len(result["sub_questions"]) == 3
    assert result["trial_findings"] and result["literature_findings"] and result["outcomes_findings"]
    assert result["final_answer"]
    assert 0.0 <= result["confidence"] <= 1.0
    agents = [t["agent"] for t in result["trace"]]
    assert agents[0] == "planner" and agents[-1] == "synthesis"
    assert {"trial", "literature", "outcomes", "evaluator"} <= set(agents)


def test_empty_source_triggers_bounded_retry(monkeypatch):
    monkeypatch.setattr(mock_sources, "query_literature", lambda q: [])
    result = run_pipeline("anything")
    evals = [t for t in result["trace"] if t["agent"] == "evaluator"]
    assert result["retry_count"] == 2                 # retried up to the guard
    assert len(evals) == 3 and evals[-1]["decision"] == "synthesise"
    assert result["final_answer"]                     # still answers, no crash


def test_raising_source_returns_empty(monkeypatch):
    def boom(q):
        raise RuntimeError("zetaris down")
    monkeypatch.setattr(mock_sources, "query_trials", boom)
    fn, _ = loader.get_source("trials")
    assert fn("x") == []


def test_conform_enforces_contract():
    rows = _conform([{"pmid": 123, "abstract": "a" * 2000, "extra": "drop me"}], CONTRACT["literature"])
    assert set(rows[0]) == set(CONTRACT["literature"]["keys"])
    assert rows[0]["pmid"] == "123" and rows[0]["journal"] == ""
    assert len(rows[0]["abstract"]) == 800 and rows[0]["abstract"].endswith("...")


def test_world_model_synonyms():
    wm = WorldModel()
    wm.add_entity("T2DM", "condition")
    assert wm.find_entity("type 2 diabetes")[0]["name"] == "type 2 diabetes"
    assert "type 2 diabetes" in wm.normalize("ACE inhibitors in T2DM patients")


def test_hmem_filters_by_provenance():
    mem = HMem.session()
    mem.write({"x": 1}, provenance={"source": "PubMed"})
    mem.write({"x": 2}, provenance={"source": "ClinicalTrials.gov"})
    assert [r["content"]["x"] for r in mem.query(filters={"source": "PubMed"})] == [1]


def test_markovian_bounds_carryover():
    mk = Markovian(max_carryover_chars=50)
    mk.start_task("goal")
    for i in range(5):
        mk.next_step(None, "x" * 40, label=str(i))
    assert len(mk.get_carryover()) <= 50 and len(mk.get_trace()) == 5


@pytest.mark.parametrize("text,expected", [
    ('<think>hmm</think>```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! {"a": [1, 2]} hope that helps', {"a": [1, 2]}),
    ("no json here", None),
])
def test_extract_json(text, expected):
    import re
    assert extract_json(re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)) == expected
