"""Treatment outcomes data source — Zetaris → ClinicalTrials.gov results API fallback.

Primary path:
  Zetaris proxy API (http://localhost:3000/api/proxy/query/sql/start) executes a
  Lightning SQL query against the registered REST data source for ClinicalTrials.gov
  results (lightning.ct_results.study_results).

Fallback path (when Zetaris is not running or returns empty):
  Derive outcome summaries by querying ClinicalTrials.gov v2 for studies with results
  (filter.advanced AREA[ResultsFirstSubmitDate]), then map to the outcomes contract.

Mock path (when USE_MOCK_DATA=true or OFFLINE=true):
  Handled by loader.py routing to mock_sources before this module is imported.

Contract (enforced by loader._conform):
  keys: condition, treatment, outcome_metric, value,
        population_age_group, n_patients, source_dataset
  limit: 30 rows
"""
import json
import logging
import os
import urllib.parse
import urllib.request

import config
from data.sources import zetaris_client

log = logging.getLogger(__name__)

_OUTCOMES_NAMESPACE = os.getenv("ZETARIS_OUTCOMES_NAMESPACE", "ct_results")

# ---------------------------------------------------------------------------
# ClinicalTrials.gov results API fallback
# ---------------------------------------------------------------------------

_CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"
_CT_RESULTS_FIELDS = (
    "NCTId,Condition,InterventionName,PrimaryOutcomeMeasure,"
    "PrimaryOutcomeTimeFrame,EnrollmentCount,MinimumAge,MaximumAge"
)


def _age_group(min_age: str, max_age: str) -> str:
    """Map age strings to a coarse population group."""
    def _years(s: str) -> float | None:
        s = s.strip().lower()
        if not s or s == "n/a":
            return None
        try:
            val = float("".join(c for c in s if c.isdigit() or c == "."))
        except ValueError:
            return None
        if "month" in s:
            val /= 12
        return val

    lo, hi = _years(min_age), _years(max_age)
    if lo is not None and lo < 18:
        return "Pediatric"
    if hi is not None and hi <= 65:
        return "Adult"
    if lo is not None and lo >= 65:
        return "Elderly"
    return "Adult"


def _ct_results_direct(sub_question: str, limit: int = 30) -> list[dict]:
    """Query ClinicalTrials.gov for studies-with-results and map to outcomes schema."""
    params = urllib.parse.urlencode({
        "query.term": sub_question,
        "filter.advanced": "AREA[ResultsFirstSubmitDate]RANGE[MIN,MAX]",
        "fields": _CT_RESULTS_FIELDS,
        "pageSize": min(limit, 100),
        "format": "json",
    })
    url = f"{_CT_API_BASE}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())

    studies = body.get("studies", [])
    rows = []
    for s in studies:
        proto = s.get("protocolSection", {})
        id_mod = proto.get("identificationModule", {})
        design_mod = proto.get("designModule", {})
        elig_mod = proto.get("eligibilityModule", {})
        conds_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})
        outcomes_mod = proto.get("outcomesModule", {})

        conditions = ", ".join(conds_mod.get("conditions", []))
        interventions = arms_mod.get("interventions", [{}])
        treatment = interventions[0].get("name", "") if interventions else ""
        primary = outcomes_mod.get("primaryOutcomes", [{}])
        metric = primary[0].get("measure", "") if primary else ""
        timeframe = primary[0].get("timeFrame", "") if primary else ""
        value = timeframe  # best proxy without parsed numeric results
        enrollment = str(design_mod.get("enrollmentInfo", {}).get("count", ""))
        min_age = elig_mod.get("minimumAge", "")
        max_age = elig_mod.get("maximumAge", "")
        nct_id = id_mod.get("nctId", "")

        rows.append({
            "condition": conditions,
            "treatment": treatment,
            "outcome_metric": metric,
            "value": value,
            "population_age_group": _age_group(min_age, max_age),
            "n_patients": enrollment,
            "source_dataset": f"ClinicalTrials.gov {nct_id}",
        })
    return rows[:limit]


# ---------------------------------------------------------------------------
# Zetaris row normaliser
# ---------------------------------------------------------------------------

def _parse_zetaris_outcomes_rows(raw_rows: list[dict]) -> list[dict]:
    """Normalise raw Zetaris rows to contract schema.

    The ct_results.study_results REST table may return:
    - A raw JSON blob from ClinicalTrials.gov in a 'studies' column (same shape
      as ct_gov.ct_studies), from which we extract results fields.
    - Flat projected columns already matching (or close to) the contract keys.
    """
    result = []
    for row in raw_rows:
        # Case 1: raw ClinicalTrials.gov JSON blob in a 'studies' column
        if "studies" in row:
            studies_val = row["studies"]
            if isinstance(studies_val, str):
                try:
                    studies_val = json.loads(studies_val)
                except Exception:
                    continue
            if not isinstance(studies_val, list):
                studies_val = [studies_val] if isinstance(studies_val, dict) else []
            for s in studies_val:
                parsed = _parse_ct_study_outcomes(s)
                if parsed:
                    result.append(parsed)
            continue

        # Case 2: flat columns projected by Zetaris
        result.append({
            "condition": str(row.get("condition", row.get("Condition", ""))),
            "treatment": str(row.get("treatment", row.get("interventionName", row.get("InterventionName", "")))),
            "outcome_metric": str(row.get("outcome_metric", row.get("primaryOutcomeMeasure", row.get("PrimaryOutcomeMeasure", "")))),
            "value": str(row.get("value", row.get("primaryOutcomeTimeFrame", row.get("PrimaryOutcomeTimeFrame", "")))),
            "population_age_group": str(row.get("population_age_group", row.get("ageGroup", "Adult"))),
            "n_patients": str(row.get("n_patients", row.get("enrollmentCount", row.get("EnrollmentCount", "")))),
            "source_dataset": str(row.get("source_dataset", row.get("nctId", "ClinicalTrials.gov"))),
        })
    return result


def _parse_ct_study_outcomes(s: dict) -> dict | None:
    """Extract outcomes-schema fields from a single ClinicalTrials.gov study object."""
    proto = s.get("protocolSection", {})
    if not proto:
        return None
    id_mod = proto.get("identificationModule", {})
    design_mod = proto.get("designModule", {})
    elig_mod = proto.get("eligibilityModule", {})
    conds_mod = proto.get("conditionsModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    outcomes_mod = proto.get("outcomesModule", {})

    conditions = ", ".join(conds_mod.get("conditions", []))
    interventions = arms_mod.get("interventions", [{}])
    treatment = interventions[0].get("name", "") if interventions else ""
    primary = outcomes_mod.get("primaryOutcomes", [{}])
    metric = primary[0].get("measure", "") if primary else ""
    timeframe = primary[0].get("timeFrame", "") if primary else ""
    enrollment = str(design_mod.get("enrollmentInfo", {}).get("count", ""))
    min_age = elig_mod.get("minimumAge", "")
    max_age = elig_mod.get("maximumAge", "")
    nct_id = id_mod.get("nctId", "")

    return {
        "condition": conditions,
        "treatment": treatment,
        "outcome_metric": metric,
        "value": timeframe,
        "population_age_group": _age_group(min_age, max_age),
        "n_patients": enrollment,
        "source_dataset": f"ClinicalTrials.gov {nct_id}",
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def query_outcomes(sub_question: str) -> list[dict]:
    """Return up to 30 treatment outcome records matching sub_question.

    Tries Zetaris first (lightning.ct_results.study_results);
    falls back to ClinicalTrials.gov results API.
    loader._conform will enforce exact keys and length caps.
    """
    # --- Zetaris path ---
    if not config.OFFLINE:
        try:
            safe_q = sub_question.replace("'", "''")
            sql = (
                f"SELECT * FROM {_OUTCOMES_NAMESPACE}.study_results "
                f"WHERE query = '{safe_q}' LIMIT 30"
            )
            raw_rows = zetaris_client.query(sql, page_limit=30)
            if raw_rows:
                rows = _parse_zetaris_outcomes_rows(raw_rows)
                if rows:
                    log.info("outcomes: %d rows from Zetaris", len(rows))
                    return rows
            log.info("outcomes: Zetaris returned 0 rows, trying direct API")
        except Exception as exc:
            log.warning("outcomes: Zetaris unavailable (%s), using direct API", exc)

    # --- Direct API fallback ---
    try:
        rows = _ct_results_direct(sub_question)
        log.info("outcomes: %d rows from ClinicalTrials.gov results", len(rows))
        return rows
    except Exception as exc:
        log.warning("outcomes: direct API also failed (%s)", exc)
        return []
