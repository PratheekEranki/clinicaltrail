# ClinicalTrail — Interface Contract

> The handshake between Pratheek (agents) and Sai Teja (data layer).
> This file defines exactly what Sai Teja delivers and what Pratheek expects.
> Neither side needs to know how the other half works internally.

---

## The Three Functions

Sai Teja implements these. Pratheek calls them. They live in `data/sources/`.

---

### `query_trials(sub_question: str) → list[dict]`

**File:** `data/sources/clinical_trials.py`

**Called by:** Trial Agent (`agents/trial.py`)

**Input:** A natural-language sub-question targeting ClinicalTrials.gov
- Example: `"clinical trials on ACE inhibitors in elderly diabetic patients with cardiovascular outcomes"`

**Returns:** A list of dicts, each with **exactly** these keys:

| Key | Type | Example | Notes |
|-----|------|---------|-------|
| `nct_id` | str | `"NCT04521413"` | ClinicalTrials.gov identifier |
| `title` | str | `"Cardiovascular Effects of..."` | Brief title, max 500 chars |
| `phase` | str | `"Phase 3"` | Trial phase |
| `status` | str | `"Completed"` | Overall status |
| `primary_outcome` | str | `"MACE reduction at 12 months"` | Primary endpoint |
| `enrollment` | str | `"2400"` | Number of participants |
| `condition` | str | `"Type 2 Diabetes"` | Target condition |
| `intervention` | str | `"Lisinopril 10mg"` | Intervention/drug |
| `start_date` | str | `"2021-03-01"` | Trial start date |

**Rules:**
- Return `[]` on any error — never raise
- Missing fields: use empty string `""`, not `None`
- Max 20 results
- Truncate any string field over 500 chars

---

### `query_literature(sub_question: str) → list[dict]`

**File:** `data/sources/pubmed.py`

**Called by:** Literature Agent (`agents/literature.py`)

**Input:** A natural-language sub-question targeting PubMed
- Example: `"published research on ACE inhibitors elderly diabetes cardiovascular mortality"`

**Returns:** A list of dicts, each with **exactly** these keys:

| Key | Type | Example | Notes |
|-----|------|---------|-------|
| `pmid` | str | `"35841234"` | PubMed ID |
| `title` | str | `"ACE Inhibition and Cardiovascular..."` | Article title |
| `abstract` | str | `"Background: ..."` | Max 800 chars — truncate with "..." |
| `publication_date` | str | `"2023-06-15"` | Publication date |
| `journal` | str | `"NEJM"` | Journal name |
| `authors` | str | `"Smith J, Jones A, ..."` | Author list |

**Rules:**
- Return `[]` on any error — never raise
- Missing fields: use empty string `""`, not `None`
- Max 15 results, ordered by date descending
- Abstract truncated to 800 chars

---

### `query_outcomes(sub_question: str) → list[dict]`

**File:** `data/sources/outcomes.py`

**Called by:** Outcomes Agent (`agents/outcomes.py`)

**Input:** A natural-language sub-question targeting outcomes data
- Example: `"population outcomes for diabetes patients on cardiovascular treatment"`

**Returns:** A list of dicts, each with **exactly** these keys:

| Key | Type | Example | Notes |
|-----|------|---------|-------|
| `condition` | str | `"Type 2 Diabetes"` | Patient condition |
| `treatment` | str | `"ACE Inhibitor"` | Treatment/drug class |
| `outcome_metric` | str | `"MACE at 5 years"` | What was measured |
| `value` | str | `"18.3%"` | Outcome value |
| `population_age_group` | str | `"65-80"` | Age group |
| `n_patients` | str | `"12400"` | Sample size |
| `source_dataset` | str | `"CDC_NHANES_2022"` | Dataset name |

**Rules:**
- Return `[]` on any error — never raise
- Missing fields: use empty string `""`, not `None`
- Max 30 results

---

## Integration Timeline

| When | What happens |
|------|-------------|
| Day 1 end | Sai Teja: ClinicalTrials.gov working in Zetaris. Shares env key names with Pratheek. |
| Day 2 | Pratheek: uses mock data in agents. Sai Teja: wires all 3 sources. |
| Day 2 end | Sai Teja: all 3 functions return real rows when called directly. Commits files. |
| Day 3 morning | **Handoff:** Pratheek pulls from repo, replaces mock data with Sai Teja's functions. |
| Day 3 afternoon | Full pipeline runs on real data. Both debug together if queries return wrong results. |
| Day 4 | Sai Teja does clean-repo test. Pratheek handles edge cases in agent logic. |

---

## Mock Data (Pratheek uses this until Day 3)

Until Sai Teja's functions are ready, Pratheek's agents use this:

**Mock `query_trials` return:**
```
[
  { "nct_id": "NCT_MOCK_001", "title": "Mock Trial: ACE Inhibitors in Elderly Diabetics",
    "phase": "Phase 3", "status": "Completed", "primary_outcome": "MACE reduction",
    "enrollment": "2400", "condition": "Type 2 Diabetes", "intervention": "Lisinopril",
    "start_date": "2020-01-01" }
]
```

**Mock `query_literature` return:**
```
[
  { "pmid": "MOCK_001", "title": "Mock Paper: Cardiovascular outcomes and ACE inhibitors",
    "abstract": "Background: Mock abstract for testing...", "publication_date": "2023-01-01",
    "journal": "Mock Journal", "authors": "Smith J, et al." }
]
```

**Mock `query_outcomes` return:**
```
[
  { "condition": "Type 2 Diabetes", "treatment": "ACE Inhibitor",
    "outcome_metric": "MACE at 5 years", "value": "18.3%",
    "population_age_group": "65-80", "n_patients": "12400",
    "source_dataset": "MOCK_DATASET" }
]
```

---

## What to Do If the Interface Breaks

If Sai Teja's function returns different keys than expected:
- Pratheek's agents must not crash — they use `.get(key, "")` defensively
- Sai Teja updates his function to match the contract above
- Both agree on the fix, update this file if the contract changes

If a function raises instead of returning `[]`:
- Sai Teja adds try/except and returns `[]`
- Pratheek's agents always check `if not findings: continue`
