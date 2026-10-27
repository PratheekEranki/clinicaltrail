# ClinicalTrail

Multi-agent clinical evidence system (Open Agent Hackathon 2026 · Track 2). Ask a clinical
research question; agents query ClinicalTrials.gov, PubMed and population outcomes data,
flag contradictions between them, and return a cited, confidence-scored answer with a full
JSON reasoning trace.

```
planner → (trial ∥ literature ∥ outcomes) → evaluator ─┬─ synthesise → synthesis → answer
                     ▲                                  │
                     └──────── retry (max 2) ───────────┘
```

See `context.md`, `architecture.md` and `interface_contract.md` for the design.

---

## 1. Setup (once)

Requires Python 3.11+. Commands below are for Windows PowerShell; on macOS/Linux use
`source .venv/bin/activate` and `python3`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Credentials

| File | Committed? | Purpose |
|------|-----------|---------|
| `.env` | ✅ yes | Template — placeholders only, never real values |
| `example.env` | ❌ no (gitignored) | **Your real keys.** This is what the app loads |

```powershell
copy .env example.env      # first time only
```

Then edit `example.env` and set at least:

```
NVIDIA_API_KEY=nvapi-your-real-key
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
```

> `llama-3.3-nemotron-super-49b-v1.5` was retired on 2026-08-26 (HTTP 410), and
> `llama-3.1-nemotron-70b-instruct` returns 404 for our key. `nemotron-3.5-lightning-30b-a3b`
> is confirmed working. To list models your key can see:
> `python -c "import config,requests;print([m['id'] for m in requests.get(config.NVIDIA_BASE_URL+'/models',headers={'Authorization':'Bearer '+config.NVIDIA_API_KEY}).json()['data'] if 'nemotron' in m['id']])"`

Optional: `OPENAI_API_KEY` enables GPT-4o-mini as a fallback if Nemotron fails.
Zetaris keys are filled in by Sai Teja's data layer.

## 3. Run

```powershell
# Demo query (elderly diabetics on ACE inhibitors)
python main.py --demo

# Your own question
python main.py --query "Do SGLT2 inhibitors reduce heart failure hospitalisation in CKD patients?"
```

| Flag | Effect |
|------|--------|
| `--demo` | Run the built-in demo query |
| `--query "..."` / `-q` | Run your own question |
| `--mock` | Force mock data even if real data sources exist |
| `--offline` | No LLM calls at all — heuristics only (free, instant; good for testing wiring) |
| `--json` | Print the full result as JSON instead of the rich tables |

Each run uses 5 LLM calls (planner, evaluator, 2 synthesis steps, final answer), plus one
evaluator call per useful retry. Nemotron's hidden "thinking" is off by default (it was ~90%
of output tokens and ~10× the latency); set `NVIDIA_THINKING=true` in `example.env` to turn it on. Use `--offline` while working on wiring to spend zero tokens.

**Output:** tables in the terminal (sub-questions, agent trace, contradictions, answer +
confidence) and the full trace saved to `logs/trace_<timestamp>.json`.

## 4. Tests

```powershell
pytest -q
```

Tests run fully offline with mock data — no API key or tokens needed.

---

## Data sources: mock vs real

Agents call the three functions from `interface_contract.md` through `data/loader.py`:

- If `data/sources/clinical_trials.py`, `pubmed.py`, `outcomes.py` exist (Sai Teja's Zetaris
  layer), they are used automatically.
- Otherwise `data/mock_sources.py` is used. Mock data includes a deliberate disagreement
  (benefit attenuated in patients > 75) so the Evaluator has something to flag.

The trace shows which was used per agent: `data_origin: "zetaris"` or `"mock"`.
The loader also enforces the contract (exact keys, string values, length caps, `[]` on any
exception), so a misbehaving source can't crash the agents.

## Project layout

```
main.py              CLI entry point, rich output, saves trace
graph.py             LangGraph state machine + retry conditional
config.py            loads example.env (real keys), then .env (template defaults)
llm.py               Nemotron → GPT-4o-mini → heuristic fallback chain, JSON extraction
agents/
  state.py           shared PipelineState TypedDict
  planner.py         query → 3 sub-questions + entities (writes World Model)
  data_agent.py      shared logic for the 3 data agents (writes H-MEM)
  trial.py / literature.py / outcomes.py
  evaluator.py       contradictions + synthesise/retry decision (reads H-MEM)
  synthesis.py       Markovian step-through + final cited answer + confidence
  common.py          trace entries, evidence formatting
memory/              Meterless wrappers (in-process until SDK access is confirmed)
  hmem.py            H-MEM: write / query / get_all
  world_model.py     entity store + synonyms ("T2DM" = "type 2 diabetes")
  markovian.py       bounded-carryover reasoning steps
data/
  loader.py          picks real vs mock sources, enforces contract
  mock_sources.py    mock rows matching interface_contract.md
  sources/           ← Sai Teja's Zetaris functions go here
tests/test_pipeline.py
```

## How confidence is computed

`confidence = min(LLM self-reported confidence, evidence score)` where
evidence score = source coverage (sources with results ÷ 3) × (1 − contradiction penalty),
penalty = 0.03 low / 0.08 medium / 0.15 high per contradiction, capped at 0.5.
Without an LLM, confidence is the evidence score capped at 0.5. All three numbers are in the
`synthesis` step of the trace.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `410 Gone` / `404 Not found for account` | Model retired or not enabled for your key — change `NVIDIA_MODEL` in `example.env` |
| Planner shows `model: heuristic` | No working LLM — check `NVIDIA_API_KEY` in `example.env` (not `.env`) |
| `data.sources.* not available yet — using mock data` | Expected until Sai Teja's data layer is committed |
| `UnicodeEncodeError` in terminal | `set PYTHONIOENCODING=utf-8` (PowerShell: `$env:PYTHONIOENCODING="utf-8"`) |
