"""Orchestrator: runs the agents in order, checks their work and decides what happens next.

    data agent  ->  analyst agent  ->  validation (pandas)  ->  writer agent
                         ^                   |
                         +--- retry if any figure fails the check

Run:  python orchestrator.py
"""
from __future__ import annotations

import json
from datetime import datetime

from agents import analyst_agent, data_agent, writer_agent
from config import INDICATORS, MAX_ANALYST_RETRIES, OUTPUT_DIR, QUESTION, RUNS_DIR
from validate import feedback_for_analyst, report_markdown, validate_findings


def main() -> None:
    log: list[dict] = []          # every tool call and answer, for transparency
    history: list[list[dict]] = []  # validation results of each round
    OUTPUT_DIR.mkdir(exist_ok=True)
    RUNS_DIR.mkdir(exist_ok=True)

    # 1. Data agent: download, inspect, clean.
    notes = []
    for indicator, label in INDICATORS.items():
        print(f"[1/4] Data agent preparing {indicator} ...")
        note = data_agent(indicator, label, log)
        notes.append(f"{indicator} ({label}):\n{note}")
        print(note, "\n")
    data_note = "\n\n".join(notes)

    # 2 + 3. Analyst agent, checked by independent validation, with retries.
    feedback, submission, results = "", {}, []
    for attempt in range(1 + MAX_ANALYST_RETRIES):
        print(f"[2/4] Analyst agent, attempt {attempt + 1} ...")
        submission = analyst_agent(QUESTION, data_note, log, feedback)

        print("[3/4] Validating findings with pandas ...")
        results = validate_findings(submission["findings"])
        history.append(results)
        failed = [r for r in results if r["status"] != "ok"]
        print(f"      {len(results) - len(failed)} of {len(results)} findings verified.")
        if not failed:
            break
        feedback = feedback_for_analyst(results)

    # Only verified findings reach the writer.
    verified = {
        "findings": [r for r in results if r["status"] == "ok"],
        "caveats": submission.get("caveats", []),
    }

    # 4. Writer agent.
    print("[4/4] Writer agent drafting the brief ...")
    brief = writer_agent(QUESTION, verified, log)

    # Save everything.
    (OUTPUT_DIR / "brief.md").write_text(brief, encoding="utf-8")
    (OUTPUT_DIR / "validation_report.md").write_text(report_markdown(history), encoding="utf-8")
    (OUTPUT_DIR / "findings.json").write_text(json.dumps(verified, indent=2), encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (RUNS_DIR / f"run_{stamp}.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print("\nDone. See the outputs/ folder; the full agent log is in runs/.")


if __name__ == "__main__":
    main()
