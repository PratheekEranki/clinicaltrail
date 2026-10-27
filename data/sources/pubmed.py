"""PubMed literature data source — Zetaris → PubMed E-utilities fallback.

Primary path:
  Zetaris proxy API executes Lightning SQL against the registered REST source
  for PubMed E-utilities (esearch).

Fallback path (when Zetaris is not running or returns empty):
  Direct call to NCBI E-utilities (esearch → efetch).

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
from data.sources import zetaris_client

log = logging.getLogger(__name__)

_PM_NAMESPACE = os.getenv("ZETARIS_PM_NAMESPACE", "pubmed")

# ---------------------------------------------------------------------------
# PubMed E-utilities direct fallback
# ---------------------------------------------------------------------------

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_EMAIL = os.getenv("NCBI_EMAIL", "clinicaltrail@hackathon.local")
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
            "authors": "; ".join(authors[:5]),
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
    # pubmed.esearch is a REST data source registered in Zetaris that wraps PubMed
    # E-utilities.  The REST table returns raw XML in a '_corrupt_record' column
    # and does not support column-level WHERE filters (db/term are URL params, not
    # projected columns).  We query the table without a filter to confirm connectivity,
    # then parse the XML to extract PMIDs and efetch full article details.
    if not config.OFFLINE:
        try:
            sql = f"SELECT * FROM {_PM_NAMESPACE}.esearch LIMIT 15"
            raw_rows = zetaris_client.query(sql, page_limit=15)
            if raw_rows:
                rows = _parse_zetaris_pm_rows(raw_rows, sub_question)
                if rows:
                    log.info("pubmed: %d rows from Zetaris (via esearch XML)", len(rows))
                    return rows
            log.info("pubmed: Zetaris returned 0/unparseable rows, trying direct API")
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


def _parse_zetaris_pm_rows(raw_rows: list[dict], sub_question: str = "") -> list[dict]:
    """Normalise raw Zetaris rows to contract schema.

    The pubmed.esearch table returns raw XML in '_corrupt_record' (Zetaris name for
    unparsed REST responses).  We parse the PubMed eSearch XML to extract PMIDs,
    then efetch full article details.  Falls back to direct esearch if no PMIDs found.
    """
    result = []
    for row in raw_rows:
        # Case 1: raw XML in '_corrupt_record' (Zetaris REST passthrough)
        raw_xml = row.get("_corrupt_record", "")
        if raw_xml and isinstance(raw_xml, str) and "<eSearchResult" in raw_xml:
            try:
                root = ET.fromstring(raw_xml)
                pmids = [el.text for el in root.findall(".//Id") if el.text]
                if pmids:
                    fetched = _efetch(pmids[:15])
                    result.extend(fetched)
            except Exception as e:
                log.debug("pubmed: failed to parse Zetaris XML: %s", e)
            continue

        # Case 2: esearchresult JSON blob
        if "esearchresult" in row:
            er = row["esearchresult"]
            if isinstance(er, str):
                try:
                    er = json.loads(er)
                except Exception:
                    continue
            pmids = er.get("idlist", []) if isinstance(er, dict) else []
            if pmids:
                try:
                    fetched = _efetch(pmids[:15])
                    result.extend(fetched)
                except Exception:
                    pass
            continue

        # Case 3: flat columns already projected by Zetaris
        result.append({
            "pmid": str(row.get("pmid", row.get("Id", ""))),
            "title": str(row.get("title", row.get("Title", ""))),
            "abstract": str(row.get("abstract", row.get("Abstract", ""))),
            "publication_date": str(row.get("publication_date", row.get("PubDate", ""))),
            "journal": str(row.get("journal", row.get("Journal", ""))),
            "authors": str(row.get("authors", row.get("Authors", ""))),
        })
    return result
