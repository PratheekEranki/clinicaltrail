"""PubMed literature data source — Zetaris → PubMed E-utilities fallback.

Primary path:
  Zetaris REST API executes Lightning SQL against a registered REST source
  for PubMed E-utilities (esearch + efetch).

Fallback path (when Zetaris is not running):
  Direct call to NCBI E-utilities (esearch → efetch).

Mock path (when USE_MOCK_DATA=true or OFFLINE=true):
  Handled by loader.py routing to mock_sources before this module is imported.

Contract (enforced by loader._conform):
  keys: pmid, title, abstract, publication_date, journal, authors
  limit: 15 rows
"""
import json
import logging
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zetaris REST helpers (shared pattern — identical to clinical_trials.py)
# ---------------------------------------------------------------------------

_ZETARIS_REST_URL = os.getenv("ZETARIS_REST_URL", "http://localhost:8888/api/v1.0")
_ZETARIS_API_KEY = os.getenv("ZETARIS_API_KEY", "")
_ZETARIS_USERNAME = os.getenv("ZETARIS_USERNAME", "dev@account.com")
_ZETARIS_PASSWORD = os.getenv("ZETARIS_PASSWORD", "password")

# The Lightning SQL namespace where we registered PubMed E-utilities.
# Register once:
#   CREATE LIGHTNINGDB pubmed USING rest OPTIONS (
#     url 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils',
#     format 'xml'
#   );
_PM_NAMESPACE = os.getenv("ZETARIS_PM_NAMESPACE", "lightning.pubmed")


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
# PubMed E-utilities direct fallback
# ---------------------------------------------------------------------------

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_EMAIL = os.getenv("NCBI_EMAIL", "clinicaltrail@hackathon.local")  # required by NCBI TOS
_NCBI_TOOL = "ClinicalTrailAgent"


def _esearch(query: str, retmax: int = 15) -> list[str]:
    """Return up to retmax PMIDs for the query."""
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
        "tool": _NCBI_TOOL,
        "email": _NCBI_EMAIL,
    })
    url = f"{_EUTILS_BASE}/esearch.fcgi?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode())
    return body.get("esearchresult", {}).get("idlist", [])


def _efetch(pmids: list[str]) -> list[dict]:
    """Fetch article details for a list of PMIDs; return structured dicts."""
    if not pmids:
        return []
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "abstract",
        "tool": _NCBI_TOOL,
        "email": _NCBI_EMAIL,
    })
    url = f"{_EUTILS_BASE}/efetch.fcgi?{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml_bytes = resp.read()

    root = ET.fromstring(xml_bytes)
    rows = []
    for article in root.findall(".//PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        pmid_el = citation.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else ""
        art = citation.find("Article")
        if art is None:
            continue
        title_el = art.find("ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""

        abstract_texts = [
            "".join(t.itertext())
            for t in art.findall(".//AbstractText")
        ]
        abstract = " ".join(abstract_texts)

        journal = art.findtext("Journal/Title", "")
        pub_date_el = art.find("Journal/JournalIssue/PubDate")
        if pub_date_el is not None:
            year = pub_date_el.findtext("Year", "")
            month = pub_date_el.findtext("Month", "")
            pub_date = f"{year}-{month}" if month else year
        else:
            pub_date = ""

        author_list = art.find("AuthorList")
        authors = []
        if author_list is not None:
            for a in author_list.findall("Author"):
                last = a.findtext("LastName", "")
                fore = a.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {fore}".strip())
        rows.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "publication_date": pub_date,
            "journal": journal,
            "authors": "; ".join(authors[:5]),  # cap at 5 authors
        })
    return rows


def _pubmed_direct(sub_question: str, limit: int = 15) -> list[dict]:
    pmids = _esearch(sub_question, retmax=limit)
    time.sleep(0.34)  # NCBI rate limit: max 3 req/sec without API key
    return _efetch(pmids)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def query_literature(sub_question: str) -> list[dict]:
    """Return up to 15 PubMed article records matching sub_question.

    Tries Zetaris first; falls back to PubMed E-utilities direct.
    loader._conform will enforce exact keys and length caps.
    """
    # --- Zetaris path ---
    if not config.OFFLINE:
        try:
            safe_q = sub_question.replace("'", "''")
            sql = f"""
                SELECT pmid,
                       title,
                       abstract,
                       publicationDate AS publication_date,
                       journal,
                       authors
                FROM   {_PM_NAMESPACE}
                WHERE  query = '{safe_q}'
                LIMIT  15
            """
            rows = _zetaris_query(sql.strip())
            if rows:
                log.info("pubmed: %d rows from Zetaris", len(rows))
                return rows
            log.info("pubmed: Zetaris returned 0 rows, trying direct API")
        except Exception as exc:
            log.warning("pubmed: Zetaris unavailable (%s), using direct API", exc)

    # --- Direct API fallback ---
    try:
        rows = _pubmed_direct(sub_question)
        log.info("pubmed: %d rows from PubMed E-utilities", len(rows))
        return rows
    except Exception as exc:
        log.warning("pubmed: direct API also failed (%s)", exc)
        return []
