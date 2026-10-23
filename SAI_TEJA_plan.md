# Sai Teja's Plan — Data Layer Owner

> Your half of ClinicalTrail. Read `context.md` and `architecture.md` first.
> Pratheek's plan is in `PRATHEEK_plan.md`.

---

## What You Own

- Zetaris Cloud Gateway setup and connectivity
- All three data source integrations:
  - `data/sources/clinical_trials.py` → ClinicalTrials.gov via Zetaris
  - `data/sources/pubmed.py` → PubMed via Zetaris
  - `data/sources/outcomes.py` → open outcomes Parquet/CSV via Zetaris
- `data/zetaris_client.py` — shared Zetaris connection helper (JDBC singleton)
- `data/schema/` — Lightning SQL schema docs for each source
- `scripts/verify_zetaris.py` — connectivity test script that others run to confirm your work
- Data validation: clean nulls, truncate long fields, never raise (always return `[]` on error)
- Clean-repo test on Day 4 (fresh clone, verify it all works)

## What You Hand Pratheek

Three Python functions. He calls them from his agents. You build them.

```
query_trials(sub_question: str)     → list[dict]
query_literature(sub_question: str) → list[dict]
query_outcomes(sub_question: str)   → list[dict]
```

### Return shapes (exactly these keys — Pratheek's agents depend on them):

**query_trials:**
```
{ nct_id, title, phase, status, primary_outcome,
  enrollment, condition, intervention, start_date }
```

**query_literature:**
```
{ pmid, title, abstract, publication_date, journal, authors }
```

**query_outcomes:**
```
{ condition, treatment, outcome_metric, value,
  population_age_group, n_patients, source_dataset }
```

### Rules each function must follow:
- Takes a natural-language sub-question string
- Parses it into SQL-friendly keywords
- Runs a Zetaris Lightning SQL query
- Returns clean, validated dicts (no nulls causing crashes)
- **Returns `[]` on any error — never raises an exception**
- Truncate long string fields (abstracts: 800 chars max, others: 500 chars max)

---

## Zetaris — How It Works

Zetaris Cloud Gateway lets you treat external APIs and files as SQL tables. You connect via JDBC and run Lightning SQL queries against "virtual" tables that proxy the real data sources.

```
Your Python code
      │
      │  (JDBC connection on port 9993)
      ▼
  Zetaris Cloud Gateway
      │
      ├── clinical_trials  (REST source → ClinicalTrials.gov API)
      ├── pubmed_articles  (REST source → PubMed E-utilities)
      └── outcomes_data    (Parquet/CSV source → health outcomes file)
```

You define the sources inside Zetaris. Once defined, `SELECT * FROM clinical_trials WHERE condition LIKE '%diabetes%'` just works.

---

## Day-by-Day Plan

### Day 1 — 22 Oct (Today): Get Zetaris Connected
- [ ] **Sign up for Zetaris Cloud Gateway** — HackOS Resources > Zetaris > "How to Sign Up"
- [ ] Download and install the platform (follow the resource guide)
- [ ] Clone the getting-started repo they provide:
  ```
  git clone https://github.com/zetaris/getting-started
  cd getting-started
  cp .env.example .env.local
  # Fill in your credentials
  ```
- [ ] Run their preflight check: `python3 scripts/preflight.py --jdbc`
  - JDBC must pass. REST failures alone don't block you today.
- [ ] Verify with a manual SQL test:
  ```sql
  SELECT 1;
  SHOW LIGHTNING DATABASES;
  ```
- [ ] Wire **ClinicalTrials.gov** as your first REST source
  - Use the "Zetaris: Your First Data Source (PokéAPI)" guide in Resources as the pattern
  - Base URL: `https://clinicaltrials.gov/api/v2/studies`
  - Test: `SELECT COUNT(*) FROM clinical_trials WHERE condition LIKE '%diabetes%'`
- [ ] Write `data/zetaris_client.py` — shared JDBC connection helper (singleton `get_client()`)
- [ ] Write `data/schema/clinical_trials_schema.sql` — document the fields you expose
- [ ] **End-of-day:** DM Pratheek the `.env` key names he needs to fill in

### Day 2 — 23 Oct: Wire All Three Sources
- [ ] Wire **PubMed** as a REST source
  - Base URL: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`
  - Key endpoints: `esearch.fcgi` (search for PMIDs) + `efetch.fcgi` (fetch abstracts)
  - Test: `SELECT COUNT(*) FROM pubmed_articles WHERE abstract LIKE '%cardiovascular%'`
- [ ] Wire **Outcomes Dataset** as a Parquet/CSV source
  - Check HackOS Resources > Zetaris > "Zetaris Open Data: Parquet and CSV Sources"
  - Or: download a CDC/WHO health outcomes CSV and load as a Zetaris CSV source
  - Test: `SELECT DISTINCT condition FROM outcomes_data LIMIT 20`
- [ ] Write `data/sources/clinical_trials.py` — full `query_trials()` function
- [ ] Write `data/sources/pubmed.py` — full `query_literature()` function
- [ ] Write `data/sources/outcomes.py` — full `query_outcomes()` function
- [ ] Write schema files for PubMed and outcomes
- [ ] **Share credentials with Pratheek via DM (not in repo)**
- [ ] **End-of-day:** all three functions return real rows when called directly from Python

### Day 3 — 24 Oct: Integration + Handoff
- [ ] Run `scripts/verify_zetaris.py` — all 3 sources must pass
- [ ] Share your 3 function files with Pratheek (commit to shared repo)
- [ ] Be available for integration questions — Pratheek will wire your functions into his agents
- [ ] If any query returns wrong/empty results, debug Zetaris-side (SQL, source config)
- [ ] Tune keyword extraction in your functions based on what queries Pratheek's agents send
- [ ] Test with the demo query sub-questions:
  - Trials: "clinical trials on ACE inhibitors in elderly diabetic patients cardiovascular outcomes"
  - Literature: "published research ACE inhibitors elderly diabetes cardiovascular"
  - Outcomes: "population outcomes diabetes cardiovascular ACE inhibitor treatment"

### Day 4 — 25 Oct: Hardening + Clean-Repo Test
- [ ] Handle edge cases in each function: no results, null fields, network timeout
- [ ] Validate that every returned dict has exactly the expected keys (no missing keys)
- [ ] Do a **clean-repo test**: fresh clone, fill `.env`, run `verify_zetaris.py` — everything must pass
- [ ] Write `tests/test_zetaris.py` — basic assertions on return shapes from all 3 functions
- [ ] Review `data/schema/` — make sure schema files reflect what Zetaris actually returns

### Day 5 — 26 Oct: Demo Support
- [ ] Run the terminal during demo recording (Pratheek narrates)
- [ ] Know how to show a Zetaris SQL query in the demo (judges will ask about it)
- [ ] Slides: your section = Zetaris architecture diagram + data source explanation

---

## Zetaris Client — What It Needs to Do

You'll write this in `data/zetaris_client.py`.

```
ZetarisClient(host, port, database, user, password, driver_path)
  .connect()           → opens JDBC connection
  .query(sql, timeout) → returns list[dict] or [] on error
  .close()             → closes connection

get_client()           → returns singleton ZetarisClient (connects on first call)
```

The singleton pattern means all three data sources share one connection — no connection pool needed for the hackathon.

---

## Lightning SQL Patterns

These are the query patterns your functions will use. Adapt column names to match what your Zetaris sources actually expose.

**Keyword extraction from sub-question:**
- Strip stopwords (what, does, the, a, an, of, in, on, for, and, or, is, are, with...)
- Take the remaining significant tokens
- Cap at 4–5 keywords for the WHERE clause (avoid oversized queries)

**ClinicalTrials.gov — keyword search:**
```sql
SELECT nct_id, title, phase, status, primary_outcome,
       enrollment, condition, intervention, start_date
FROM clinical_trials
WHERE (condition LIKE '%diabetes%' OR title LIKE '%diabetes%')
  AND (condition LIKE '%cardiovascular%' OR title LIKE '%cardiovascular%')
LIMIT 20
```

**PubMed — AND keyword search:**
```sql
SELECT pmid, title, abstract, publication_date, journal, authors
FROM pubmed_articles
WHERE (title LIKE '%ace inhibitor%' OR abstract LIKE '%ace inhibitor%')
  AND (title LIKE '%diabetes%' OR abstract LIKE '%diabetes%')
ORDER BY publication_date DESC
LIMIT 15
```

**Outcomes — condition + treatment filter:**
```sql
SELECT condition, treatment, outcome_metric, value,
       population_age_group, n_patients, source_dataset
FROM outcomes_data
WHERE condition LIKE '%diabetes%'
  AND treatment LIKE '%ace%'
LIMIT 30
```

---

## Troubleshooting Guide

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| JDBC connection refused | Zetaris Gateway not running | Start the gateway process |
| `Operation not permitted` | Wrong JDBC driver path | Check `ZETARIS_DRIVER_PATH` in `.env` |
| Empty results from a source | Source not registered in Zetaris | Go to Zetaris UI, check your data sources |
| Column not found | Your Zetaris source exposes different column names | Run `DESCRIBE clinical_trials` in Zetaris, update your SELECT |
| REST source returns no data | Base URL or endpoint path wrong in Zetaris config | Re-check the source setup against the PokéAPI guide |
| jaydebeapi ImportError | Not installed | `pip install jaydebeapi` |

---

## Cursor Prompts to Use

**For wiring ClinicalTrials.gov in Zetaris:**
> I'm setting up ClinicalTrials.gov as a REST data source in Zetaris. The base URL is `https://clinicaltrials.gov/api/v2/studies`. The key query params are `query.cond` (condition) and `query.intr` (intervention). Show me how to configure this in Zetaris as a REST source following the PokéAPI pattern from the getting-started guide, and write a test SQL query.

**For debugging empty results:**
> My Zetaris Lightning SQL query against the ClinicalTrials.gov REST source returns empty results. Here is my SQL: [paste SQL]. Here is the Zetaris source configuration: [paste config]. What could cause this and how do I debug it?

**For keyword extraction:**
> I have a natural-language sub-question: "clinical trials on ACE inhibitors in elderly diabetic patients with cardiovascular outcomes". Write a Python function to extract 4–5 SQL-friendly keywords from it, filtering out stopwords, for use in a LIKE WHERE clause.

**For parsing PubMed as a two-step source:**
> I need to wire PubMed E-utilities as a Zetaris REST source. The flow is: 1) call `esearch.fcgi` with a query term to get PMIDs, 2) call `efetch.fcgi` with those PMIDs to get article details including abstracts. How do I represent this two-step REST flow as a single Zetaris data source?

---

## Security Rule

**Never commit credentials to the repo.** This means:
- `example.env` holds real credentials and is in `.gitignore` — never add it to git
- `.env` is the committed template — placeholders only, never real values
- Share Zetaris credentials with Pratheek via **direct message only**
- Your Zetaris host, port, database name, username, and password stay out of all files in the repo
