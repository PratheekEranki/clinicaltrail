"""Treatment outcomes data source — Zetaris → synthesised from ClinicalTrials.gov results.

Primary path:
  Zetaris REST API executes Lightning SQL against aggregated outcomes data
  registered as a REST/CSV source in Zetaris (e.g. from ClinicalTrials.gov
  results databases or linked publications).

Fallback path (when Zetaris is not running):
  Derive outcome summaries by querying ClinicalTrials.gov v2 for results
  sections (studiesWithResults endpoint), then map to the outcomes contract.

Mock path (when USE_MOCK_DATA=true or OFFLINE=true):
  Handled by loader.py routing to mock_sources before this module is imported.

Contract (enforced by loader._conform):
  keys: condition, treatment, outcome_metric, value,
        population_age_group, n_patients, source_dataset
  limit: 30 rows

Note on the Zetaris namespace:
  Register ClinicalTrials.gov results as a second REST source:
    CREATE LIGHTNINGDB ct_results USING rest OPTIONS (
      url 'https://clinicaltrials.gov/api/v2/studies',
      format 'json'
    );
  The Lightning SQL query below targets {_OUTCOMES_NAMESPACE}.
"""
import json
import logging
import os
import urllib.parse
import urllib.request

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zetaris REST helpers
# ---------------------------------------------------------------------------

_ZETARIS_REST_URL = os.getenv("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0")
_ZETARIS_API_KEY = os.getenv("ZETARIS_API_KEY", "")
_ZETARIS_USERNAME = os.getenv("ZETARIS_USERNAME", "dev@account.com")
_ZETARIS_PASSWORD = os.getenv("ZETARIS_PASSWORD", "password")

_OUTCOMES_NAMESPACE = os.getenv("ZETARIS_OUTCOMES_NAMESPACE", "lightning.ct_results")


def _zetaris_auth_header() -> dict:
    if _ZETARIS_API_KEY:
        return {"Authorization": f"Bearer {_ZETARIS_API_KEY}"}
    import base64
    creds = base64.b64encode(f"{_ZETARIS_USERNAME}:{_ZETARIS_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


def _zetaris_query(sql: str, timeout: int = 30) -> list[dict]:
    url = f"{_ZETARIS_REST_URL}/query"
    payload = json.dumps({"sql": sql}).encode()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **_zetaris_auth_header(),
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    cols = body.get("columns", [])
    rows = body.get("data", [])
    return [dict(zip(cols, row)) for row in rows]


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
        value = timeframe  # timeframe is the closest proxy without parsed results
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
# Public interface
# ---------------------------------------------------------------------------

def query_outcomes(sub_question: str) -> list[dict]:
    """Return up to 30 treatment outcome records matching sub_question.

    Tries Zetaris first; falls back to ClinicalTrials.gov results API.
    loader._conform will enforce exact keys and length caps.
    """
    # --- Zetaris path ---
    if not config.OFFLINE:
        try:
            safe_q = sub_question.replace("'", "''")
            sql = f"""
                SELECT condition,
                       interventionName    AS treatment,
                       primaryOutcomeMeasure AS outcome_metric,
                       primaryOutcomeTimeFrame AS value,
                       ageGroup            AS population_age_group,
                       enrollmentCount     AS n_patients,
                       CONCAT('ClinicalTrials.gov ', nctId) AS source_dataset
                FROM   {_OUTCOMES_NAMESPACE}
                WHERE  query = '{safe_q}'
                  AND  hasResults = true
                LIMIT  30
            """
            rows = _zetaris_query(sql.strip())
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
