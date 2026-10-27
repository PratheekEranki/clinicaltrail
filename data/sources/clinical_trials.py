"""Clinical trials data source — Zetaris → ClinicalTrials.gov public API fallback.

Primary path:
  Zetaris REST API (http://localhost:8888/api/v1.0) executes a Lightning SQL query
  against a registered REST data source for ClinicalTrials.gov.

Fallback path (when Zetaris is not running):
  Direct call to the ClinicalTrials.gov v2 REST API.

Mock path (when USE_MOCK_DATA=true or OFFLINE=true):
  Not handled here — loader.py routes to mock_sources before this module is imported.

Contract (enforced by loader._conform):
  keys: nct_id, title, phase, status, primary_outcome,
        enrollment, condition, intervention, start_date
  limit: 20 rows
"""
import logging
import os
import urllib.parse
import urllib.request
import json

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zetaris REST helpers
# ---------------------------------------------------------------------------

_ZETARIS_REST_URL = os.getenv("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0")
_ZETARIS_API_KEY = os.getenv("ZETARIS_API_KEY", "")
_ZETARIS_USERNAME = os.getenv("ZETARIS_USERNAME", "dev@account.com")
_ZETARIS_PASSWORD = os.getenv("ZETARIS_PASSWORD", "password")

# The Lightning SQL namespace where we registered ClinicalTrials.gov as a REST source.
# Register once via the Zetaris GUI or via:
#   CREATE LIGHTNINGDB ct_gov USING rest OPTIONS (
#     url 'https://clinicaltrials.gov/api/v2/studies',
#     format 'json'
#   );
_CT_NAMESPACE = os.getenv("ZETARIS_CT_NAMESPACE", "lightning.ct_gov")


def _zetaris_auth_header() -> dict:
    """Return HTTP auth header for Zetaris REST API."""
    if _ZETARIS_API_KEY:
        return {"Authorization": f"Bearer {_ZETARIS_API_KEY}"}
    import base64
    creds = base64.b64encode(f"{_ZETARIS_USERNAME}:{_ZETARIS_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


def _zetaris_query(sql: str, timeout: int = 30) -> list[dict]:
    """Execute a Lightning SQL query via Zetaris REST and return rows as dicts."""
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
    # Zetaris returns {"data": [[...], ...], "columns": [...]}
    cols = body.get("columns", [])
    rows = body.get("data", [])
    return [dict(zip(cols, row)) for row in rows]


# ---------------------------------------------------------------------------
# ClinicalTrials.gov direct API fallback
# ---------------------------------------------------------------------------

_CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"
_CT_FIELDS = (
    "NCTId,BriefTitle,Phase,OverallStatus,PrimaryOutcomeMeasure,"
    "EnrollmentCount,Condition,InterventionName,StartDate"
)


def _ct_direct(sub_question: str, limit: int = 20) -> list[dict]:
    """Query ClinicalTrials.gov v2 API directly (fallback when Zetaris is down)."""
    params = urllib.parse.urlencode({
        "query.term": sub_question,
        "fields": _CT_FIELDS,
        "pageSize": limit,
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
        stat_mod = proto.get("statusModule", {})
        design_mod = proto.get("designModule", {})
        outcomes_mod = proto.get("outcomesModule", {})
        conds_mod = proto.get("conditionsModule", {})
        arms_mod = proto.get("armsInterventionsModule", {})
        primary = outcomes_mod.get("primaryOutcomes", [{}])
        interventions = arms_mod.get("interventions", [{}])
        rows.append({
            "nct_id": id_mod.get("nctId", ""),
            "title": id_mod.get("briefTitle", ""),
            "phase": ", ".join(design_mod.get("phases", [])),
            "status": stat_mod.get("overallStatus", ""),
            "primary_outcome": primary[0].get("measure", "") if primary else "",
            "enrollment": str(design_mod.get("enrollmentInfo", {}).get("count", "")),
            "condition": ", ".join(conds_mod.get("conditions", [])),
            "intervention": interventions[0].get("name", "") if interventions else "",
            "start_date": stat_mod.get("startDateStruct", {}).get("date", ""),
        })
    return rows


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def query_trials(sub_question: str) -> list[dict]:
    """Return up to 20 clinical trial records matching sub_question.

    Tries Zetaris first; falls back to ClinicalTrials.gov direct API.
    loader._conform will enforce the exact keys and length caps.
    """
    # --- Zetaris path ---
    if not config.OFFLINE:
        try:
            # Lightning SQL: query ct_gov REST source via Zetaris
            safe_q = sub_question.replace("'", "''")
            sql = f"""
                SELECT nctId        AS nct_id,
                       briefTitle   AS title,
                       phase,
                       overallStatus AS status,
                       primaryOutcome AS primary_outcome,
                       enrollmentCount AS enrollment,
                       condition,
                       interventionName AS intervention,
                       startDate    AS start_date
                FROM   {_CT_NAMESPACE}
                WHERE  query = '{safe_q}'
                LIMIT  20
            """
            rows = _zetaris_query(sql.strip())
            if rows:
                log.info("clinical_trials: %d rows from Zetaris", len(rows))
                return rows
            log.info("clinical_trials: Zetaris returned 0 rows, trying direct API")
        except Exception as exc:
            log.warning("clinical_trials: Zetaris unavailable (%s), using direct API", exc)

    # --- Direct API fallback ---
    try:
        rows = _ct_direct(sub_question)
        log.info("clinical_trials: %d rows from ClinicalTrials.gov direct API", len(rows))
        return rows
    except Exception as exc:
        log.warning("clinical_trials: direct API also failed (%s)", exc)
        return []
