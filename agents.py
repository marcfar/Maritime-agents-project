"""The agent loop and the three agents.

An "agent" here is a model call with a role (system prompt) and a set of tools.
The loop is always the same:
    1. send the conversation to the model
    2. if the model asks for a tool, run it and send the result back
    3. repeat until the model answers in plain text (or submits its findings)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

from config import MAX_AGENT_TURNS, MAX_TOKENS, MODEL
from tools import ANALYSIS_TOOLS, DATA_TOOLS, run_tool



def _load_env_file() -> None:
    """Read ANTHROPIC_API_KEY from a local .env file, if there is one."""
    env = Path(__file__).parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env_file()
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


def run_agent(name: str, system: str, task: str, tools: list, log: list, final_tool: str | None = None):
    """Run one agent until it finishes. Returns its final text, or the input of
    `final_tool` if the agent ends by calling that tool."""
    messages = [{"role": "user", "content": task}]

    for _ in range(MAX_AGENT_TURNS):
        kwargs = {"model": MODEL, "max_tokens": MAX_TOKENS, "system": system, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        response = client.messages.create(**kwargs)

        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            if final_tool:
                # The agent stopped without submitting (it answered in prose or ran
                # out of tokens). Remind it to hand in its result through the tool.
                log.append({"agent": name, "event": "reminder", "stop_reason": response.stop_reason, "text": text})
                messages.append({"role": "assistant", "content": text or "I have finished my analysis."})
                messages.append({"role": "user", "content": f"Do not answer in text. Call the {final_tool} tool now."})
                continue
            log.append({"agent": name, "event": "final_text", "text": text})
            return text

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == final_tool:
                log.append({"agent": name, "event": "submitted", "input": block.input})
                return block.input
            output = run_tool(block.name, block.input)
            log.append({"agent": name, "event": "tool_call", "tool": block.name, "input": block.input, "output": json.loads(output)})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
        messages.append({"role": "user", "content": results})

    raise RuntimeError(f"Agent '{name}' did not finish in {MAX_AGENT_TURNS} turns.")


# --------------------------------------------------------------------------- #
# Agent 1: data
# --------------------------------------------------------------------------- #
DATA_SYSTEM = """You are a data engineer preparing a dataset for analysis.
Download the indicator, inspect its quality profile, and decide the cleaning rules.
Think about: aggregates that would double count countries, missing values, and the
last year with enough country coverage to compare countries fairly.
Then create the clean file and check its profile.
Finish with a short data-quality note: what you removed and why, and any limitation
the analyst must know. Do not analyse the data."""


def data_agent(indicator: str, label: str, log: list) -> str:
    task = (
        f"Prepare indicator {indicator}, whose official name is '{label}'. "
        "Use that exact name whenever you refer to it."
    )
    return run_agent("data", DATA_SYSTEM, task, DATA_TOOLS, log)


# --------------------------------------------------------------------------- #
# Agent 2: analyst
# --------------------------------------------------------------------------- #
ANALYST_SYSTEM = """You are a quantitative analyst working for a maritime observatory.
Answer the question using only the tools. Every number you report must come from a
tool result; never estimate or recall figures from memory.
When you are done, call submit_findings with 8 to 12 findings.
Each finding must contain exactly one figure: the one you put in `number`, for the
country, indicator and years you state. Do not mention any other figure, rank or
comparison in the claim, because only that one figure is checked.
When you report growth, use min_start_value to leave out countries that start from
very small values."""


def analyst_agent(question: str, data_note: str, log: list, feedback: str = "") -> dict:
    task = f"Question: {question}\n\nData-quality note from the data engineer:\n{data_note}"
    if feedback:
        task += f"\n\nYour previous findings failed an independent check. Fix them:\n{feedback}"
    return run_agent("analyst", ANALYST_SYSTEM, task, ANALYSIS_TOOLS, log, final_tool="submit_findings")


# --------------------------------------------------------------------------- #
# Agent 3: writer
# --------------------------------------------------------------------------- #
WRITER_SYSTEM = """You write short policy briefs for readers who are not data specialists.
Write in Markdown, under 400 words: a title, a two-sentence summary, the findings in
plain language, and a 'Limitations' section with the caveats.
Use only the validated findings you are given. The only figure you may quote from
each finding is its `number`. Do not state ranks, totals or comparisons that are not
in the findings, and do not add figures of your own."""


def writer_agent(question: str, findings: dict, log: list) -> str:
    task = f"Question: {question}\n\nValidated findings (JSON):\n{json.dumps(findings, indent=2)}"
    return run_agent("writer", WRITER_SYSTEM, task, [], log)
