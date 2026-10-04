"""Tools the agents are allowed to call.

Each tool is an ordinary Python function plus a JSON schema that tells the model
what the tool does and which arguments it takes. The agents never run free code:
they can only call these functions, which keeps the pipeline predictable.
"""
from __future__ import annotations

import json

import pandas as pd
import requests

from config import DATA_DIR, INDICATORS

WB_API = "https://api.worldbank.org/v2"
RAW = DATA_DIR / "raw.csv"
CLEAN = DATA_DIR / "clean.csv"


# --------------------------------------------------------------------------- #
# Data tools (used by the data agent)
# --------------------------------------------------------------------------- #

def _save_indicator(path, new_rows: pd.DataFrame, indicator: str) -> None:
    """Add one indicator's rows to a CSV, replacing earlier rows of that indicator."""
    if path.exists():
        old = pd.read_csv(path)
        old = old[old["indicator"] != indicator]
        new_rows = pd.concat([old, new_rows], ignore_index=True)
    new_rows.to_csv(path, index=False)

def download_indicator(indicator: str) -> dict:
    """Download one World Bank indicator for all countries and save it as CSV."""
    if indicator not in INDICATORS:
        return {"error": f"Unknown indicator. Allowed: {list(INDICATORS)}"}

    url = f"{WB_API}/country/all/indicator/{indicator}"
    payload = requests.get(url, params={"format": "json", "per_page": 20000}, timeout=60).json()
    rows = [
        {
            "indicator": indicator,
            "country_code": r["countryiso3code"],
            "country": r["country"]["value"],
            "year": int(r["date"]),
            "value": r["value"],
        }
        for r in payload[1]
    ]
    df = pd.DataFrame(rows)

    # Regions and income groups ("World", "Euro area"...) are flagged as aggregates.
    meta = requests.get(f"{WB_API}/country", params={"format": "json", "per_page": 400}, timeout=60).json()
    aggregates = {c["id"] for c in meta[1] if c["region"]["value"] == "Aggregates"}
    df["is_aggregate"] = df["country_code"].isin(aggregates) | (df["country_code"] == "")

    DATA_DIR.mkdir(exist_ok=True)
    _save_indicator(RAW, df, indicator) 
    return profile_dataset("raw", indicator)


def profile_dataset(which: str, indicator: str) -> dict:
    """Describe a dataset so the agent can judge its quality."""
    path = RAW if which == "raw" else CLEAN
    if not path.exists():
        return {"error": f"{path.name} does not exist yet."}
    df = pd.read_csv(path)
    df = df[df["indicator"] == indicator]
    if df.empty:
        return {"error": f"No rows for {indicator} in {path.name}."}
    per_year = df.dropna(subset=["value"]).groupby("year")["country_code"].nunique()
    return {
        "file": path.name,
        "rows": len(df),
        "countries": int(df["country_code"].nunique()),
        "aggregate_rows": int(df["is_aggregate"].sum()) if "is_aggregate" in df else 0,
        "missing_values": int(df["value"].isna().sum()),
        "year_min": int(df["year"].min()),
        "year_max": int(df["year"].max()),
        "countries_with_data_per_year": {int(y): int(n) for y, n in per_year.tail(12).items()},
        "indicator": indicator
    }


def clean_dataset(indicator: str, drop_aggregates: bool, min_year: int, max_year: int, drop_missing: bool) -> dict:
    """Apply the cleaning decisions taken by the data agent and save clean.csv."""
    df = pd.read_csv(RAW)
    df = df[df["indicator"] == indicator]
    if drop_aggregates:
        df = df[~df["is_aggregate"]]
    df = df[(df["year"] >= min_year) & (df["year"] <= max_year)]
    if drop_missing:
        df = df.dropna(subset=["value"])
    df = df.drop(columns=["is_aggregate"]).sort_values(["country_code", "year"])
    _save_indicator(CLEAN, df, indicator)
    return profile_dataset("clean", indicator)


# --------------------------------------------------------------------------- #
# Analysis tools (used by the analyst agent)
# --------------------------------------------------------------------------- #
def _clean() -> pd.DataFrame:
    return pd.read_csv(CLEAN)


def top_countries(indicator: str, year: int, n: int = 10) -> dict:
    """The n countries with the highest value in a given year."""
    df = _clean()
    top = df[(df["year"] == year) & (df["indicator"] == indicator)].nlargest(n, "value")
    return {"year": year, "indicator": indicator, "top": top[["country_code", "country", "value"]].to_dict("records")}


def growth_table(indicator: str, start_year: int, end_year: int, min_start_value: float = 0) -> dict:
    """Percentage change between two years for every country that has both."""
    df = _clean()
    df = df[df["indicator"] == indicator].pivot(index="country_code", columns="year", values="value")
    both = df[[start_year, end_year]].dropna()
    both = both[both[start_year] >= min_start_value]
    both["growth_pct"] = (both[end_year] / both[start_year] - 1) * 100
    both = both.sort_values("growth_pct", ascending=False).round(2)
    records = both.reset_index().rename(columns={start_year: "start", end_year: "end"})
    return {
        "start_year": start_year,
        "end_year": end_year,
        "n_countries": len(records),
        "fastest": records.head(10).to_dict("records"),
        "slowest": records.tail(10).to_dict("records"),
    }


def country_series(indicator: str, country_code: str) -> dict:
    """The full time series of one country (ISO3 code, e.g. 'SWE')."""
    df = _clean()
    df = df[df["indicator"] == indicator]
    s = df[df["country_code"] == country_code.upper()]
    return {"country_code": country_code.upper(), "series": s[["year", "value"]].to_dict("records")}


def correlation(year: int) -> dict:
    """Spearman rank correlation between the two indicators across countries in one year."""
    df = _clean()
    wide = df[df["year"] == year].pivot(index="country_code", columns="indicator", values="value").dropna()
    if wide.shape[1] < 2 or len(wide) < 3:
        return {"error": f"Not enough countries with both indicators in {year}."}
    a, b = wide.columns
    rho = wide[a].rank().corr(wide[b].rank())
    return {"year": year, "n_countries": len(wide), "spearman": round(float(rho), 3)}


# --------------------------------------------------------------------------- #
# Schemas: what the model sees
# --------------------------------------------------------------------------- #
DATA_TOOLS = [
    {
        "name": "download_indicator",
        "description": "Download a World Bank indicator for all countries and return a quality profile of the raw file.",
        "input_schema": {
            "type": "object",
            "properties": {"indicator": {"type": "string", "description": "Indicator code, e.g. IS.SHP.GOOD.TU"}},
            "required": ["indicator"],
        },
    },
    {
        "name": "profile_dataset",
        "description": "Return row counts, missing values, year range and coverage per year for the raw or clean file.",
        "input_schema": {
            "type": "object",
            "properties": {"indicator": {"type": "string"}, "which": {"type": "string", "enum": ["raw", "clean"]}},
            "required": ["indicator", "which"],
        },
    },
    {
        "name": "clean_dataset",
        "description": "Create the clean file from the raw one using the cleaning rules you choose.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "drop_aggregates": {"type": "boolean", "description": "Remove regions and income groups such as 'World'."},
                "min_year": {"type": "integer"},
                "max_year": {"type": "integer", "description": "Last year with good country coverage."},
                "drop_missing": {"type": "boolean"},
            },
            "required": ["indicator", "drop_aggregates", "min_year", "max_year", "drop_missing"],
        },
    },
]

ANALYSIS_TOOLS = [
    {
        "name": "top_countries",
        "description": "Top n countries by value in one year of a specific indicator.",
        "input_schema": {
            "type": "object",
            "properties": {"indicator":{"type": "string"}, "year": {"type": "integer"}, "n": {"type": "integer"}},
            "required": ["indicator","year"],
        },
    },
    {
        "name": "growth_table",
        "description": "Percentage growth of an indicator between two years per country; returns the 10 fastest and 10 slowest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator":{"type": "string"},
                "start_year": {"type": "integer"},
                "end_year": {"type": "integer"},
                "min_start_value": {"type": "number", "description": "Ignore countries below this value in the start year."},
            },
            "required": ["indicator", "start_year", "end_year"],
        },
    },
    {
        "name": "country_series",
        "description": "Time series of the indicator for one country by ISO3 code.",
        "input_schema": {
            "type": "object",
            "properties": {"indicator":{"type": "string"}, "country_code": {"type": "string"}},
            "required": ["indicator", "country_code"],
        },
    },
    {
        "name": "correlation",
        "description": "Spearman rank correlation between the two indicators across countries, for a year in which both have data.",
        "input_schema": {
            "type": "object",
            "properties": {"year": {"type": "integer"}},
            "required": ["year"],
        },
    },
    {
        "name": "submit_findings",
        "description": "Submit your final findings. Call this exactly once, when your analysis is complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "claim": {"type": "string", "description": "One sentence a policy reader can understand."},
                            "indicator": {"type": "string"},
                            "metric": {"type": "string", "enum": ["value", "growth_pct", "spearman_corr"]},
                            "country_code": {"type": "string", "description": "ISO3 code"},
                            "year": {"type": "integer", "description": "For metric 'value'."},
                            "start_year": {"type": "integer", "description": "For metric 'growth_pct'."},
                            "end_year": {"type": "integer", "description": "For metric 'growth_pct'."},
                            "number": {"type": "number", "description": "The figure the claim relies on."},
                        },
                        "required": ["claim", "metric", "number"],
                    },
                },
                "caveats": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["findings", "caveats"],
        },
    },
]

FUNCTIONS = {
    "download_indicator": download_indicator,
    "profile_dataset": profile_dataset,
    "clean_dataset": clean_dataset,
    "top_countries": top_countries,
    "growth_table": growth_table,
    "country_series": country_series,
    "correlation": correlation,
}


def run_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return its result as JSON text for the model."""
    try:
        result = FUNCTIONS[name](**arguments)
    except Exception as exc:  # the agent sees the error and can react to it
        result = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps(result, default=str)
