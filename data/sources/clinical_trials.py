"""Clinical trials data source — Zetaris → ClinicalTrials.gov public API fallback.

Primary path:
  Zetaris proxy API (http://localhost:3000/api/proxy/query/sql/start) executes a
  Lightning SQL query against the registered REST data source for ClinicalTrials.gov.

Fallback path (when Zetaris is not running or returns empty):
  Direct call to the ClinicalTrials.gov v2 REST API.

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
from data.sources import zetaris_client

log = logging.getLogger(__name__)

# Lightning SQL namespace registered in Zetaris for ClinicalTrials.gov
_CT_NAMESPACE = os.getenv("ZETARIS_CT_NAMESPACE", "ct_gov")

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
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": f"ClinicalTrail {os.getenv('NCBI_EMAIL', 'clinicaltrail@hackathon.local')}",
    })
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
            safe_q = sub_question.replace("'", "''")
            # ct_gov.ct_studies returns nextPageToken + studies (raw JSON from ClinicalTrials.gov)
            # We SELECT the raw JSON blob and parse it; or use the nested column if Zetaris flattens it.
            sql = (
                f"SELECT * FROM {_CT_NAMESPACE}.ct_studies "
                f"WHERE query = '{safe_q}' LIMIT 20"
            )
            raw_rows = zetaris_client.query(sql, page_limit=20)
            if raw_rows:
                rows = _parse_zetaris_ct_rows(raw_rows)
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


def _parse_zetaris_ct_rows(raw_rows: list[dict]) -> list[dict]:
    """Normalise raw Zetaris rows to the contract schema.

    The ct_gov.ct_studies REST table returns the ClinicalTrials.gov JSON blob
    as a 'studies' column (and nextPageToken).  Try to parse it; if the columns
    are already flat (Zetaris projected them), map them directly.
    """
    result = []
    for row in raw_rows:
        # Case 1: Zetaris returned the raw JSON blob in a 'studies' column
        if "studies" in row:
            studies_val = row["studies"]
            if isinstance(studies_val, str):
                try:
                    studies_val = json.loads(studies_val)
                except Exception:
                    continue
            if isinstance(studies_val, list):
                for s in studies_val:
                    parsed = _parse_ct_study(s)
                    if parsed:
                        result.append(parsed)
            elif isinstance(studies_val, dict):
                parsed = _parse_ct_study(studies_val)
                if parsed:
                    result.append(parsed)
            continue

        # Case 2: Zetaris projected individual columns (flat row)
        result.append({
            "nct_id": str(row.get("nctId", row.get("nct_id", ""))),
            "title": str(row.get("briefTitle", row.get("title", ""))),
            "phase": str(row.get("phase", "")),
            "status": str(row.get("overallStatus", row.get("status", ""))),
            "primary_outcome": str(row.get("primaryOutcome", row.get("primary_outcome", ""))),
            "enrollment": str(row.get("enrollmentCount", row.get("enrollment", ""))),
            "condition": str(row.get("condition", "")),
            "intervention": str(row.get("interventionName", row.get("intervention", ""))),
            "start_date": str(row.get("startDate", row.get("start_date", ""))),
        })
    return result


def _parse_ct_study(s: dict) -> dict | None:
    """Parse a single study object from the ClinicalTrials.gov studies array."""
    proto = s.get("protocolSection", {})
    if not proto:
        return None
    id_mod = proto.get("identificationModule", {})
    stat_mod = proto.get("statusModule", {})
    design_mod = proto.get("designModule", {})
    outcomes_mod = proto.get("outcomesModule", {})
    conds_mod = proto.get("conditionsModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    primary = outcomes_mod.get("primaryOutcomes", [{}])
    interventions = arms_mod.get("interventions", [{}])
    return {
        "nct_id": id_mod.get("nctId", ""),
        "title": id_mod.get("briefTitle", ""),
        "phase": ", ".join(design_mod.get("phases", [])),
        "status": stat_mod.get("overallStatus", ""),
        "primary_outcome": primary[0].get("measure", "") if primary else "",
        "enrollment": str(design_mod.get("enrollmentInfo", {}).get("count", "")),
        "condition": ", ".join(conds_mod.get("conditions", [])),
        "intervention": interventions[0].get("name", "") if interventions else "",
        "start_date": stat_mod.get("startDateStruct", {}).get("date", ""),
    }
