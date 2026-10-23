"""ClinicalTrail CLI.

    python main.py --query "For elderly diabetic patients on ACE inhibitors, ..."
    python main.py --demo              # runs the demo query
    python main.py --demo --mock       # force mock data
    python main.py --demo --offline    # no LLM calls (heuristics only)
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

DEMO_QUERY = ("For elderly diabetic patients on ACE inhibitors, what does recent trial evidence "
              "say about cardiovascular outcomes, and does the published literature and outcomes "
              "data confirm or contradict it?")

RESULT_KEYS = ["query", "sub_questions", "entities", "trial_findings", "literature_findings",
               "outcomes_findings", "contradictions", "final_answer", "supporting_evidence",
               "contradicting_evidence", "confidence", "retry_count", "trace"]


def parse_args():
    p = argparse.ArgumentParser(description="ClinicalTrail — explainable clinical evidence agent")
    p.add_argument("--query", "-q", help="clinical research question")
    p.add_argument("--demo", action="store_true", help="run the built-in demo query")
    p.add_argument("--mock", action="store_true", help="force mock data sources")
    p.add_argument("--offline", action="store_true", help="skip LLM calls, use heuristics")
    p.add_argument("--json", action="store_true", help="print the full result as JSON only")
    args = p.parse_args()
    if not args.query and not args.demo:
        p.error("provide --query or --demo")
    return args


def save_trace(result: dict, log_dir) -> str:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps({k: result.get(k) for k in RESULT_KEYS}, indent=2, default=str),
                    encoding="utf-8")
    return str(path)


def render(result: dict, trace_path: str) -> None:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    c = Console()
    c.print(Panel(result["query"], title="Query", border_style="cyan"))

    sq = Table(title="Planner → sub-questions", show_lines=True)
    sq.add_column("Source"); sq.add_column("Sub-question")
    for src, q in zip(["ClinicalTrials.gov", "PubMed", "Outcomes"], result.get("sub_questions", [])):
        sq.add_row(src, q)
    c.print(sq)

    agents = Table(title="Agent trace")
    for col in ("Agent", "Retry", "Model / origin", "Results", "Notes"):
        agents.add_column(col)
    for t in result.get("trace", []):
        notes = t.get("reasoning") or t.get("action") or t.get("sub_question", "")
        if t["agent"] == "evaluator":
            notes = f"decision={t.get('decision')} · {notes}"
        agents.add_row(t["agent"], str(t.get("retry", "")),
                       str(t.get("model") or t.get("data_origin", "")),
                       str(t.get("results_count", t.get("contradictions", ""))), str(notes)[:90])
    c.print(agents)

    contradictions = result.get("contradictions", [])
    if contradictions:
        ct = Table(title="Contradictions", show_lines=True)
        for col in ("Severity", "Source A", "Claim A", "Source B", "Claim B"):
            ct.add_column(col)
        colors = {"high": "red", "medium": "yellow", "low": "green"}
        for x in contradictions:
            ct.add_row(f"[{colors.get(x['severity'], 'white')}]{x['severity']}[/]",
                       x["source_a"], x["claim_a"], x["source_b"], x["claim_b"])
        c.print(ct)
    else:
        c.print("[dim]No contradictions flagged.[/dim]")

    conf = result.get("confidence", 0.0)
    color = "green" if conf >= 0.7 else "yellow" if conf >= 0.4 else "red"
    c.print(Panel(result.get("final_answer", ""), title=f"Answer · confidence [{color}]{conf:.2f}[/]",
                  border_style=color))
    c.print(f"[dim]Full trace: {trace_path}[/dim]")


def main():
    args = parse_args()
    # set before config is imported so the flags take effect
    if args.mock:
        os.environ["USE_MOCK_DATA"] = "true"
    if args.offline:
        os.environ["CLINICALTRAIL_OFFLINE"] = "true"

    import config
    from graph import run_pipeline
    import llm

    logging.basicConfig(level=config.LOG_LEVEL, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not llm.available() and not config.OFFLINE:
        logging.warning("No LLM key found in example.env — running with heuristics only")

    result = run_pipeline(args.query or DEMO_QUERY)
    trace_path = save_trace(result, config.LOG_DIR)

    if args.json:
        print(json.dumps({k: result.get(k) for k in RESULT_KEYS}, indent=2, default=str))
    else:
        render(result, trace_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
