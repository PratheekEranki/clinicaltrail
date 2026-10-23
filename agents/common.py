"""Helpers shared by agents: trace entries and compact evidence formatting."""
import time
from datetime import datetime, timezone


def trace_entry(agent: str, started: float, **details) -> dict:
    return {
        "agent": agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        **details,
    }


def fmt_trials(rows: list[dict]) -> str:
    return "\n".join(
        f"- [{r.get('nct_id', '')}] {r.get('title', '')} | {r.get('phase', '')}, {r.get('status', '')} | "
        f"n={r.get('enrollment', '')} | intervention: {r.get('intervention', '')} | "
        f"primary outcome: {r.get('primary_outcome', '')}"
        for r in rows
    ) or "(no trial results)"


def fmt_literature(rows: list[dict]) -> str:
    return "\n".join(
        f"- [PMID {r.get('pmid', '')}] {r.get('title', '')} ({r.get('journal', '')}, "
        f"{r.get('publication_date', '')}): {r.get('abstract', '')}"
        for r in rows
    ) or "(no literature results)"


def fmt_outcomes(rows: list[dict]) -> str:
    return "\n".join(
        f"- [{r.get('source_dataset', '')}] {r.get('condition', '')} / {r.get('treatment', '')} | "
        f"{r.get('outcome_metric', '')} = {r.get('value', '')} | age {r.get('population_age_group', '')} | "
        f"n={r.get('n_patients', '')}"
        for r in rows
    ) or "(no outcomes results)"


def fmt_contradictions(rows: list[dict]) -> str:
    return "\n".join(
        f"- [{c.get('severity', '')}] {c.get('source_a', '')}: {c.get('claim_a', '')} "
        f"VS {c.get('source_b', '')}: {c.get('claim_b', '')}"
        for c in rows
    ) or "(no contradictions flagged)"
