"""Resolves the three data functions: Sai Teja's real ones if present, else mocks.

Every result is passed through `_conform` so agents can rely on the contract
(exact keys, string values, length caps) even if a source drifts.
"""
import importlib
import logging
from typing import Callable

import config
from data import mock_sources

log = logging.getLogger(__name__)

CONTRACT = {
    "trials": {
        "module": "data.sources.clinical_trials", "func": "query_trials", "limit": 20,
        "keys": ["nct_id", "title", "phase", "status", "primary_outcome",
                 "enrollment", "condition", "intervention", "start_date"],
    },
    "literature": {
        "module": "data.sources.pubmed", "func": "query_literature", "limit": 15,
        "keys": ["pmid", "title", "abstract", "publication_date", "journal", "authors"],
    },
    "outcomes": {
        "module": "data.sources.outcomes", "func": "query_outcomes", "limit": 30,
        "keys": ["condition", "treatment", "outcome_metric", "value",
                 "population_age_group", "n_patients", "source_dataset"],
    },
}


def _conform(rows, spec: dict) -> list[dict]:
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows[: spec["limit"]]:
        if not isinstance(row, dict):
            continue
        clean = {}
        for key in spec["keys"]:
            val = row.get(key)
            val = "" if val is None else str(val)
            cap = 800 if key == "abstract" else 500
            clean[key] = val if len(val) <= cap else val[: cap - 3] + "..."
        out.append(clean)
    return out


def get_source(name: str) -> tuple[Callable[[str], list[dict]], str]:
    """Return (safe query function, origin) where origin is 'zetaris' or 'mock'."""
    spec = CONTRACT[name]
    fn, origin = getattr(mock_sources, spec["func"]), "mock"
    if not config.USE_MOCK_DATA:
        try:
            fn = getattr(importlib.import_module(spec["module"]), spec["func"])
            origin = "zetaris"
        except (ImportError, AttributeError):
            log.info("%s not available yet — using mock data", spec["module"])

    def safe(sub_question: str) -> list[dict]:
        try:
            return _conform(fn(sub_question), spec)
        except Exception as exc:  # contract says never raise; enforce it here too
            log.warning("%s raised %s — returning []", spec["func"], exc)
            return []

    return safe, origin
