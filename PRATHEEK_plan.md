# Pratheek's Plan — Agent Framework Owner

> Your half of ClinicalTrail. Read `context.md` and `architecture.md` first.
> Sai Teja's plan is in `SAI_TEJA_plan.md`.

---

## What You Own

- The LangGraph state machine and all agent orchestration (`graph.py`)
- All 6 agent files: Planner, Trial, Literature, Outcomes, Evaluator, Synthesis
- All three Meterless engine integrations: H-MEM, Markovian, World Model
- NVIDIA Nemotron as the LLM (with GPT-4o-mini as fallback)
- Structured JSON trace output
- `main.py` entry point
- Demo script and narration

## What Sai Teja Hands You

Three functions — you call them, he builds them:

```
query_trials(sub_question)     → list of trial dicts
query_literature(sub_question) → list of article dicts
query_outcomes(sub_question)   → list of outcome dicts
```

Each returns a list of dicts or `[]` on error. You handle empty gracefully. Until his Zetaris is live (Day 3), use mock data in those calls.

---

## Shared State (the contract between all agents)

Every agent reads from and writes to one shared state object. These are the fields:

```
query                   → the original user question (set at startup)
sub_questions           → list of 3 sub-questions (set by Planner)
world_model_id          → Meterless World Model session ID (set by Planner)
memory_session_id       → Meterless H-MEM session ID (set by Planner)
trial_findings          → list of dicts from Trial Agent
literature_findings     → list of dicts from Literature Agent
outcomes_findings       → list of dicts from Outcomes Agent
contradictions          → list of dicts flagged by Evaluator
retry_sub_questions     → refined queries if Evaluator wants a retry
retry_count             → int, incremented on each retry (max 2)
final_answer            → string, from Synthesis Agent
supporting_evidence     → list of dicts with source IDs
contradicting_evidence  → list of dicts with source IDs
confidence              → float 0.0–1.0
trace                   → list of agent decision logs (every agent appends to this)
```

---

## Agent Responsibilities

### Planner Agent
- Call NVIDIA Nemotron with the user query
- Ask it to produce exactly 3 sub-questions (one per data source) + extract entities
- Write entities (conditions, drugs, populations) to Meterless World Model
- Init a Meterless H-MEM session
- Populate `sub_questions`, `world_model_id`, `memory_session_id` in state

### Trial Agent
- Read `sub_questions[0]` from state
- Call `query_trials(sub_question)` — use mock data until Day 3
- Write each finding to H-MEM with provenance `{"source": "ClinicalTrials.gov"}`
- Populate `trial_findings` in state
- Append to `trace`

### Literature Agent
- Read `sub_questions[1]` from state
- Read World Model entities to ensure consistent terminology before querying
- Call `query_literature(sub_question)`
- Write to H-MEM with provenance `{"source": "PubMed"}`
- Populate `literature_findings` in state
- Append to `trace`

### Outcomes Agent
- Read `sub_questions[2]` from state
- Call `query_outcomes(sub_question)`
- Write to H-MEM with provenance `{"source": "outcomes_dataset"}`
- Populate `outcomes_findings` in state
- Append to `trace`

### Evaluator / Critic Agent
- Read ALL findings from H-MEM (or directly from state)
- Call NVIDIA Nemotron to compare the three finding sets
- Flag contradictions: `{ "claim_a", "source_a", "claim_b", "source_b", "severity": low|medium|high }`
- Decide: `"synthesise"` OR `"retry"` (only if refined sub-questions would actually help)
- Populate `contradictions`, `retry_sub_questions`, increment `retry_count` if retrying
- **Retry guard:** if `retry_count >= 2`, always return `"synthesise"`

### Synthesis Agent
- Init Meterless Markovian for this task
- Step through findings one set at a time (Trial → Literature → Outcomes → Contradictions) with compressed carryover
- Call NVIDIA Nemotron to write the final cited answer
- Final answer must: name specific NCT IDs and PMIDs, address contradictions explicitly, be readable for a non-technical clinical researcher
- Populate `final_answer`, `supporting_evidence`, `contradicting_evidence`, `confidence`
- Append final step to `trace`

---

## Day-by-Day Plan

### Day 1 — 22 Oct (Today): Foundation
- [ ] Get NVIDIA Nemotron API key from HackOS Resources > NVIDIA
- [ ] Set up Python venv, install packages: `langgraph langchain langchain-openai python-dotenv requests pydantic`
- [ ] Create repo folder structure: `agents/`, `memory/`, `data/sources/`, `scripts/`, `logs/`
- [ ] Write `agents/state.py` — the shared TypedDict (fields listed above)
- [ ] Write `main.py` — loads `.env`, accepts `--query` arg, calls `run_pipeline(query)`
- [ ] Write `graph.py` — wire all 6 nodes in LangGraph (even stubs), compile and verify it runs
- [ ] Write `agents/planner.py` — Nemotron call + entity extraction (can use mock sub-questions for now)
- [ ] **End-of-day test:** `python main.py --query "test"` completes without errors

### Day 2 — 23 Oct: Meterless + Core Agents
- [ ] Wire Meterless H-MEM: `memory/hmem.py` — session init, write, query methods
- [ ] Wire Meterless World Model: `memory/world_model.py` — assert_fact, find_entity, get_relationships
- [ ] Wire Meterless Markovian: `memory/markovian.py` — start_task, next_step, get_carryover
- [ ] Complete Planner Agent with real Nemotron call + World Model writes
- [ ] Write Trial, Literature, Outcomes agents with mock data returns
- [ ] Add structured trace logging to every agent (append to `state["trace"]`)
- [ ] **End-of-day test:** Full pipeline runs: Planner → Trial → Literature → Outcomes (with mock data)

### Day 3 — 24 Oct: Evaluator + Synthesis + Real Data
- [ ] Build Evaluator Agent with Nemotron-powered contradiction detection + retry decision
- [ ] Build Synthesis Agent with Markovian reasoning loop + Nemotron final answer
- [ ] Wire conditional edge in LangGraph: `should_retry()` function
- [ ] Replace mock data calls with Sai Teja's real Zetaris functions (coordinate with him in the morning)
- [ ] Run 3 full end-to-end queries, inspect JSON traces in `logs/`
- [ ] **End-of-day test:** Full pipeline on demo query, confidence > 0.5, no crashes

### Day 4 — 25 Oct: Hardening
- [ ] Error handling: Nemotron quota exceeded → fallback to GPT-4o-mini
- [ ] Error handling: empty results from a source → Evaluator handles gracefully
- [ ] Error handling: Meterless session failure → catch, log, don't crash
- [ ] Test edge cases: empty PubMed result, contradictory trial+outcomes data, vague query
- [ ] Finalize trace output format — clean, readable JSON
- [ ] Review README — is it reproducible from a clean clone?

### Day 5 — 26 Oct: Demo + Wrap-up
- [ ] Record demo: terminal run with the demo query, narrate each step
- [ ] Write your sections of the slide deck: architecture diagram, Meterless explanation, NVIDIA rationale
- [ ] Final review with Sai Teja — run the pipeline together on his machine from a clean clone

---

## Meterless Wrappers — What They Need to Do

You'll write these in `memory/` as Python classes. Once the real Meterless SDK is confirmed, you swap the internals — the interface stays the same.

### H-MEM (`memory/hmem.py`)
```
HMem(session_id)
  .write(content, level, provenance, confidence) → key
  .query(intent, filters)                         → list[dict]
  .get_all(level)                                 → list[dict]
```

### World Model (`memory/world_model.py`)
```
WorldModel(session_id)
  .assert_fact(subject, predicate, object) → None
  .find_entity(name, entity_type)          → list[dict]
  .get_relationships(entity_id)            → list[dict]
```

### Markovian (`memory/markovian.py`)
```
Markovian(task_id)
  .start_task(goal, constraints)              → None
  .next_step(carryover, new_context)          → dict
  .get_carryover()                            → str
  .get_trace()                                → list[dict]
```

---

## NVIDIA Nemotron Setup

In every agent that calls the LLM:

```
Model:    nvidia/llama-3.1-nemotron-70b-instruct
API base: https://integrate.api.nvidia.com/v1
Key:      NVIDIA_API_KEY from .env
Temp:     0.1 for structured outputs (Planner, Evaluator)
          0.2 for generative outputs (Synthesis)

Fallback: gpt-4o-mini via OPENAI_API_KEY if Nemotron quota runs low
```

---

## Cursor Prompts to Use

These go directly into Cursor chat with the relevant file open.

**For Trial Agent:**
> Build `agents/trial.py`. It reads `state["sub_questions"][0]`, calls `query_trials(sub_question)` (import from `data.sources.clinical_trials`), writes each result to H-MEM with provenance `{"source": "ClinicalTrials.gov"}`, appends to `state["trace"]`, and returns updated state with `trial_findings`. Use try/except — return `[]` on failure. Under 60 lines.

**For Literature Agent:**
> Same pattern as Trial Agent but reads `state["sub_questions"][1]`, calls `query_literature()` from `data.sources.pubmed`, writes to H-MEM with `{"source": "PubMed"}`. Also reads World Model entities first to normalize terminology before the query. Under 60 lines.

**For Synthesis Agent:**
> Build `agents/synthesis.py`. Init `Markovian(task_id)`. Call `start_task` with goal "Reconcile clinical evidence and produce traceable answer". Step through trial_findings, literature_findings, outcomes_findings, contradictions with `next_step`. Then call Nemotron with all summaries to produce: final_answer (cites NCT IDs and PMIDs), supporting_evidence list, contradicting_evidence list, confidence float. Return updated state.

**For parallel LangGraph fan-out:**
> I have 6 LangGraph nodes: planner, trial, literature, outcomes, evaluator, synthesis. Trial, Literature, Outcomes should run in parallel after Planner using the `Send` API. They fan back into Evaluator. Show me the `graph.py` with the parallel fan-out pattern using `langgraph.types.Send`.

---

## Demo Script

**Query to run:**
> "For elderly diabetic patients on ACE inhibitors, what does recent trial evidence say about cardiovascular outcomes, and does the published literature and outcomes data confirm or contradict it?"

**Narration beats (aim for 2:30–3:00):**
1. Show the query being entered (`python main.py --query "..."`)
2. Show Planner output — the 3 sub-questions it decomposed to
3. Show the three agents querying — mention Zetaris SQL running
4. Show Evaluator flagging a contradiction (point to the specific JSON)
5. Read the first 2–3 sentences of the final answer
6. Show the JSON trace in `logs/` — point to one specific reasoning step
7. Briefly show what happens with empty results (graceful degradation)

---

## Sync Points with Sai Teja

- **Morning check-in (daily):** what's blocked, what's done
- **Day 3 morning:** get his 3 functions, replace your mock data calls
- **Day 4 evening:** run the pipeline together on his machine from a clean clone
- **Day 5:** he runs terminal for the demo video, you narrate
