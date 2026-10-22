# ClinicalTrail — Architecture

---

## System Overview

```
User Query (natural language)
         │
         ▼
  ┌─────────────┐
  │   Planner   │  ← NVIDIA Nemotron (query decomposition + entity extraction)
  │    Agent    │  ← Meterless World Model (write entities: conditions, drugs, populations)
  └──────┬──────┘
         │  produces: sub_questions[0], sub_questions[1], sub_questions[2]
         │
    ─────┼─────────────────────────────────
    │              │                      │
    ▼              ▼                      ▼
┌────────┐   ┌───────────┐   ┌──────────────┐
│ Trial  │   │Literature │   │  Outcomes    │
│ Agent  │   │  Agent    │   │   Agent      │
│        │   │           │   │              │
│Zetaris │   │  Zetaris  │   │  Zetaris     │
│   ↓    │   │     ↓     │   │     ↓        │
│ClinTri │   │  PubMed   │   │ Parquet/CSV  │
│als.gov │   │  REST API │   │ outcomes     │
│        │   │           │   │              │
│H-MEM ↑ │   │ H-MEM ↑  │   │  H-MEM ↑    │
└────────┘   └───────────┘   └──────────────┘
    │              │                      │
    └──────────────┴──────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │    Evaluator    │  ← reads ALL findings from H-MEM
         │  / Critic Agent │  ← compares sources, flags contradictions
         │                 │  ← decides: synthesise OR retry with refined query
         └────────┬────────┘
                  │
       ┌──────────┴──────────┐
       │ retry (max 2 loops) │  ← loops back to Trial/Literature/Outcomes
       └──────────┬──────────┘
                  │ synthesise
                  ▼
         ┌─────────────────┐
         │   Synthesis     │  ← NVIDIA Nemotron (final answer generation)
         │    Agent        │  ← Meterless Markovian (bounded-context long reasoning)
         └────────┬────────┘
                  │
                  ▼
       Structured output:
       - final_answer (cited, readable)
       - supporting_evidence (list with source IDs)
       - contradicting_evidence (list with source IDs)
       - confidence (0.0 – 1.0)
       - trace (full JSON log of every agent decision)
```

---

## Agent Descriptions

### Planner Agent
- **Input:** raw user query
- **Does:** calls NVIDIA Nemotron to decompose into 3 sub-questions (one per data source); extracts medical entities (conditions, drugs, populations, outcomes)
- **Writes to:** Meterless World Model (entities), LangGraph state (sub_questions)
- **Output:** `sub_questions`, `world_model_id`, `memory_session_id`

### Trial Agent
- **Input:** `sub_questions[0]` (ClinicalTrials.gov-targeted)
- **Does:** parses sub-question into keywords → runs Zetaris Lightning SQL against ClinicalTrials.gov REST source
- **Writes to:** Meterless H-MEM (with provenance: source=ClinicalTrials.gov)
- **Output:** `trial_findings` list of dicts

### Literature Agent
- **Input:** `sub_questions[1]` (PubMed-targeted)
- **Does:** reads World Model for consistent entity terminology → Zetaris query against PubMed REST source
- **Writes to:** Meterless H-MEM (with provenance: source=PubMed)
- **Output:** `literature_findings` list of dicts

### Outcomes Agent
- **Input:** `sub_questions[2]` (outcomes-targeted)
- **Does:** extracts condition + treatment from sub-question → Zetaris query against Parquet/CSV outcomes source
- **Writes to:** Meterless H-MEM (with provenance: source=outcomes_dataset)
- **Output:** `outcomes_findings` list of dicts

### Evaluator / Critic Agent
- **Input:** reads all findings from H-MEM
- **Does:** calls NVIDIA Nemotron to compare the three finding sets; identifies contradictions with severity (low/medium/high); decides whether to synthesise now or send agents back for a refined query
- **Retry guard:** max 2 retry loops before forcing synthesis
- **Output:** `contradictions`, `retry_sub_questions` (if retrying), decision

### Synthesis Agent
- **Input:** all findings + contradictions + Markovian trace
- **Does:** uses Meterless Markovian to step through evidence sets without context overflow; calls NVIDIA Nemotron to write final cited answer
- **Output:** `final_answer`, `supporting_evidence`, `contradicting_evidence`, `confidence`, updated `trace`

---

## Data Flow

```
Query string
    → [Planner] → sub_questions (3x)
    → [Trial / Literature / Outcomes] → findings (3x lists of dicts)
    → [Evaluator] → contradictions + decision
    → [Synthesis] → answer + evidence + confidence + trace
    → logs/trace_<timestamp>.json
```

---

## Meterless Memory Roles

| Engine | Where Used | What It Enables |
|--------|-----------|-----------------|
| **H-MEM** | Trial, Literature, Outcomes write; Evaluator reads | Evaluator can compare findings without re-querying Zetaris |
| **World Model** | Planner writes; Literature Agent reads | Consistent entity terminology across sources ("T2DM" = "type 2 diabetes") |
| **Markovian** | Synthesis Agent | Multi-source reconciliation across context windows without losing findings |

---

## Zetaris Data Sources

| Source | What Zetaris Connects To | Zetaris Source Type |
|--------|-------------------------|-------------------|
| ClinicalTrials.gov | REST API v2: `https://clinicaltrials.gov/api/v2/studies` | REST source |
| PubMed | E-utilities: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/` | REST source |
| Outcomes data | Open Parquet/CSV health outcomes dataset | Parquet / CSV source |

All three are queried via Lightning SQL through the Zetaris JDBC connection.

---

## LangGraph State Machine

The whole pipeline is a **LangGraph StateGraph**. State flows through nodes; each node reads and returns a partial state update.

Key conditional: after Evaluator, `should_retry()` checks:
- If `retry_count < 2` AND refined sub-questions exist → loop back to Trial Agent
- Otherwise → proceed to Synthesis

This gives the system one chance to self-correct before producing a final answer.

---

## Output Format

```
logs/trace_<timestamp>.json
{
  "query": "...",
  "sub_questions": [...],
  "trial_findings": [...],
  "literature_findings": [...],
  "outcomes_findings": [...],
  "contradictions": [
    { "claim_a": "...", "source_a": "ClinicalTrials.gov", "claim_b": "...", "source_b": "PubMed", "severity": "medium" }
  ],
  "final_answer": "...",
  "supporting_evidence": [...],
  "contradicting_evidence": [...],
  "confidence": 0.78,
  "trace": [
    { "agent": "planner", "sub_questions": [...], "entities": {...} },
    { "agent": "trial", "query": "...", "results_count": 12 },
    ...
  ]
}
```
