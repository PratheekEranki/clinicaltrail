# ClinicalTrail — Project Context

> Open Agent Hackathon 2026 · Team ICHIGO · Track 2: The Agent That Can Explain Why
> Build window: 22 Oct 00:00 UTC – 27 Oct 23:45 UTC · Submission deadline: 27 Oct 23:45 UTC

---

## The Problem We're Solving

Clinical researchers waste weeks manually cross-referencing three fragmented data sources:
- **ClinicalTrials.gov** — what trials say
- **PubMed** — what published literature says
- **Population outcomes datasets** — what real-world data says

The same question asked across all three often returns conflicting evidence. There's no tool that reconciles them, cites the contradictions, and explains its reasoning.

---

## Our Solution: ClinicalTrail

A **multi-agent system** that:
1. Takes a complex clinical research question
2. Breaks it into sub-questions for each data source
3. Dispatches specialist agents to query all three simultaneously
4. Has a critic agent reconcile and flag contradictions
5. Produces a **cited, confidence-scored answer with a full reasoning trace**

The answer tells you not just *what* the evidence says but *why* the system concluded what it did — and where it disagreed.

**Example query:**
> "For elderly diabetic patients on ACE inhibitors, what does recent trial evidence say about cardiovascular outcomes, and does the published literature and outcomes data confirm or contradict it?"

---

## Why Track 2 — The Agent That Can Explain Why

Track 2 asks: can the agent explain its reasoning, not just return an answer?

ClinicalTrail is built for this:
- Every agent decision is logged to a structured JSON trace
- Contradictions between sources are surfaced explicitly with severity ratings
- The final answer names specific source IDs (NCT IDs, PMIDs)
- Confidence score reflects how much the sources agree

---

## Hackathon Judging Criteria

| Criterion | Points | How we score here |
|-----------|--------|-------------------|
| Impact | 30 | Clinical research is a real, high-stakes domain with a clear workflow problem |
| Technical | 20 | LangGraph state machine, parallel agents, retry loop, Meterless memory |
| Innovation | 15 | Multi-agent contradiction reconciliation is novel in clinical AI |
| Demo | 15 | Terminal demo showing live query → trace → contradictions → answer |
| Product & UX | 10 | Clean CLI, readable trace output, structured JSON for downstream use |
| Sponsor Tech | 10 | Zetaris (required), Meterless ×3 (required), NVIDIA Nemotron, Cursor |

---

## Sponsor Technologies We Use

| Sponsor | What We Use It For | Required? |
|---------|-------------------|-----------|
| **Zetaris** | SQL layer connecting ClinicalTrials.gov, PubMed, and outcomes Parquet/CSV. All agents query through Lightning SQL. | ✅ Yes |
| **Meterless H-MEM** | Shared hierarchical memory. Trial Agent writes → Evaluator reads without re-querying. | ✅ Yes |
| **Meterless Markovian** | Bounded-context long reasoning for Synthesis. Prevents context overflow on multi-source reconciliation. | ✅ Yes |
| **Meterless World Model** | Shared entity store — conditions, drugs, populations. Ensures "T2DM" and "type 2 diabetes" are treated as the same thing. | ✅ Yes |
| **Cursor** | Dev environment throughout. Space XAI for agent scaffolding and Zetaris query generation. | ✅ Yes |
| **NVIDIA Nemotron** | LLM for Planner and Synthesis agents. `nvidia/llama-3.1-nemotron-70b-instruct` via NVIDIA API. | Used |

---

## Team Split

| Person | What They Own |
|--------|--------------|
| **Pratheek Eranki** | LangGraph agent framework, Meterless integrations, NVIDIA Nemotron, trace output |
| **Sai Teja Koppolu** | Zetaris connectivity, all three data source integrations, SQL, data validation |

**Interface between the two:** Sai Teja delivers 3 Python functions:
- `query_trials(sub_question)` → list of trial dicts
- `query_literature(sub_question)` → list of article dicts
- `query_outcomes(sub_question)` → list of outcome dicts

Pratheek calls these from his agents. Neither needs to know how the other half works internally.

---

## Key Links

- Hackathon platform: https://hackathon.genai.works
- Zetaris resources: HackOS Resources > Zetaris
- NVIDIA API key: HackOS Resources > NVIDIA
- Meterless docs: HackOS Resources > Meterless
- Submission deadline: 27 October 2026, 23:45 UTC
