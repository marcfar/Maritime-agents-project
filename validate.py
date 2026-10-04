"""Independent check of the analyst's findings.

This is the "critical use of AI" part: nothing the analyst says reaches the brief
until its figures have been recomputed here, with plain pandas, from the clean data.
"""
from __future__ import annotations

import pandas as pd

from config import ABS_TOLERANCE, REL_TOLERANCE
from tools import CLEAN


def recompute(finding: dict, df: pd.DataFrame) -> float | None:
    """Recalculate the figure behind one finding. Returns None if it cannot be computed."""
    if finding["metric"] == "spearman_corr":
        wide = df[df["year"] == finding.get("year")].pivot(
            index="country_code", columns="indicator", values="value").dropna()
        if wide.shape[1] < 2 or len(wide) < 3:
            return None
        a, b = wide.columns
        return wide[a].rank().corr(wide[b].rank())
    
    series = df[
        (df["country_code"] == str(finding.get("country_code", "")).upper())
        & (df["indicator"] == finding.get("indicator"))
    ].set_index("year")["value"]

    if finding["metric"] == "value":
        return series.get(finding.get("year"))

    if finding["metric"] == "growth_pct":
        start, end = series.get(finding.get("start_year")), series.get(finding.get("end_year"))
        if start is None or end is None or start == 0:
            return None
        return (end / start - 1) * 100

    return None


def validate_findings(findings: list[dict]) -> list[dict]:
    """Return one result per finding: ok / mismatch / not_checkable."""
    df = pd.read_csv(CLEAN)
    results = []
    for f in findings:
        expected = recompute(f, df)
        if expected is None or pd.isna(expected):
            status = "not_checkable"
        else:
            tolerance = REL_TOLERANCE * abs(expected)
            if f["metric"] == "growth_pct":
                tolerance = max(tolerance, ABS_TOLERANCE)   # rounding of small percentages
            status = "ok" if abs(f["number"] - expected) <= tolerance else "mismatch"

        results.append({**f, "expected": None if expected is None else round(float(expected), 2), "status": status})
    return results


def feedback_for_analyst(results: list[dict]) -> str:
    """Turn the failed checks into instructions the analyst can act on."""
    lines = []
    for r in results:
        if r["status"] == "mismatch":
            lines.append(f"- '{r['claim']}': you reported {r['number']}, the data gives {r['expected']}.")
        elif r["status"] == "not_checkable":
            lines.append(f"- '{r['claim']}': could not be verified (missing year or country). Replace it.")
    return "\n".join(lines)


def report_markdown(history: list[list[dict]]) -> str:
    """A log of every validation round, to publish next to the brief."""
    out = ["# Validation report", ""]
    for i, results in enumerate(history, 1):
        ok = sum(r["status"] == "ok" for r in results)
        out += [f"## Round {i}: {ok} of {len(results)} findings verified", "",
                "| Status | Claim | Reported | Recomputed |", "| --- | --- | --- | --- |"]
        out += [f"| {r['status']} | {r['claim']} | {r['number']} | {r['expected']} |" for r in results]
        out.append("")
    return "\n".join(out)
