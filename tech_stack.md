# ClinicalTrail — Tech Stack

> What we use, why we use it, where to get access.

---

## Frameworks & Libraries

| Tool | Version | Why |
|------|---------|-----|
| **LangGraph** | ≥ 0.2.0 | State machine for multi-agent orchestration. Handles parallel fan-out, conditional edges, retry loops. Pratheek's core framework. |
| **LangChain** | ≥ 0.3.0 | Agent abstractions, LLM wrappers, prompt templates |
| **langchain-openai** | ≥ 0.2.0 | OpenAI-compatible client — used for both NVIDIA Nemotron and GPT-4o-mini fallback |
| **python-dotenv** | ≥ 1.0.0 | Load credentials from `.env` |
| **pydantic** | ≥ 2.0.0 | State validation |
| **requests / httpx** | ≥ 2.32.0 / 0.27.0 | HTTP calls |
| **pandas** | ≥ 2.0.0 | Parquet/CSV data handling |
| **jaydebeapi** | ≥ 1.2.3 | JDBC connection to Zetaris Cloud Gateway |
| **python-json-logger** | ≥ 2.0.0 | Structured JSON trace logging |
| **rich** | ≥ 13.0.0 | Terminal output formatting |

---

## Sponsor Technologies

### Zetaris (Required)
- **What:** Cloud data gateway with Lightning SQL — connects REST APIs and file sources as queryable SQL tables
- **How we use it:** All three specialist agents query through Zetaris. Removing it means no data.
- **Sources we wire:**
  - ClinicalTrials.gov REST API v2
  - PubMed E-utilities REST API
  - Open outcomes Parquet/CSV dataset
- **Connection:** JDBC on port 9993 via `jaydebeapi`
- **Access:** HackOS Resources > Zetaris > "How to Sign Up for Zetaris Cloud Gateway"
- **Owner:** Sai Teja

### Meterless H-MEM (Required)
- **What:** Hierarchical memory store shared across agents — episodic + semantic levels
- **How we use it:** Trial, Literature, Outcomes agents write findings; Evaluator reads all of them to compare without re-querying
- **Key operations:** `write(content, level, provenance, confidence)`, `query(intent, filters)`
- **Access:** HackOS Resources > Meterless
- **Owner:** Pratheek

### Meterless World Model (Required)
- **What:** Shared entity store — conditions, drugs, patient populations, relationships
- **How we use it:** Planner writes entities extracted from the query; Literature Agent reads to ensure consistent terminology ("T2DM" vs "type 2 diabetes")
- **Key operations:** `assert_fact(subject, predicate, object)`, `find_entity(name)`, `get_relationships(entity_id)`
- **Owner:** Pratheek

### Meterless Markovian (Required)
- **What:** Bounded-context long reasoning — chunks large context with compressed carryover
- **How we use it:** Synthesis Agent uses it to step through all findings across multiple reasoning steps without losing context
- **Key operations:** `start_task(goal)`, `next_step(carryover, new_context)`, `get_carryover()`, `get_trace()`
- **Owner:** Pratheek

### NVIDIA Nemotron
- **Model:** `nvidia/llama-3.1-nemotron-70b-instruct`
- **API base:** `https://integrate.api.nvidia.com/v1`
- **How we use it:** Planner (query decomposition, entity extraction) and Synthesis (final answer generation)
- **Why Nemotron:** Domain-appropriate for clinical language; outperforms GPT-4o on medical reasoning benchmarks
- **Fallback:** GPT-4o-mini (if Nemotron quota runs low)
- **Access:** HackOS Resources > NVIDIA
- **Owner:** Pratheek

### Cursor + Space XAI
- **What:** AI-powered IDE required for the hackathon
- **How we use it:** Both team members write all code in Cursor, using Space XAI for:
  - Generating LangGraph agent boilerplate
  - Writing Zetaris Lightning SQL queries
  - Debugging JDBC connection issues
  - Building the Meterless wrapper interfaces
- **Both team members need this installed**

---

## Environment Variables

All credentials go in `.env` (never committed):

```
# Zetaris (Sai Teja fills these)
ZETARIS_HOST=
ZETARIS_PORT=9993
ZETARIS_DATABASE=
ZETARIS_USER=
ZETARIS_PASSWORD=
ZETARIS_DRIVER_PATH=/path/to/lightning-jdbc-driver.jar

# NVIDIA (Pratheek fills this)
NVIDIA_API_KEY=

# Optional fallback LLM
OPENAI_API_KEY=

# Meterless (fill when SDK access is confirmed)
METERLESS_API_KEY=

# Runtime settings
LOG_LEVEL=INFO
LOG_DIR=logs
MAX_RETRY_COUNT=2
QUERY_TIMEOUT_SECONDS=10
```

> **Security rule:** Sai Teja shares Zetaris credentials with Pratheek via DM — never in the repo.

---

## Data Source Details

### ClinicalTrials.gov v2 REST API
- Base URL: `https://clinicaltrials.gov/api/v2/studies`
- No API key required
- Key params: `query.cond` (condition), `query.intr` (intervention), `pageSize`, `fields`
- Fields we use: `NCTId`, `BriefTitle`, `Phase`, `OverallStatus`, `PrimaryOutcomeMeasure`, `EnrollmentCount`, `ConditionMeshTerm`, `InterventionName`, `StartDate`

### PubMed E-utilities
- Base URLs:
  - Search: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi`
  - Fetch: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi`
- No API key required (rate-limited; key recommended for production)
- Flow: esearch → get PMIDs → efetch → get abstracts

### Outcomes Dataset (Parquet/CSV)
- Source: HackOS Resources > Zetaris > "Zetaris Open Data: Parquet and CSV Sources"
- Alternative: CDC or WHO CSV loaded as a Zetaris CSV source
- Fields we expose: `condition`, `treatment`, `outcome_metric`, `value`, `population_age_group`, `n_patients`, `source_dataset`

---

## Python Version

Python **3.11+** required (TypedDict with list[str] syntax needs 3.9+; 3.11 is safest).
