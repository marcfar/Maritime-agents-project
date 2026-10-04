"""Tests for the validation step. They need no API key: run `pytest`."""
import pandas as pd
import pytest

import tools
import validate


@pytest.fixture(autouse=True)
def sample_data(tmp_path, monkeypatch):
    df = pd.DataFrame(
    {
        "indicator": ["IS.SHP.GOOD.TU"] * 4 + ["IS.SHP.GCNW.XQ"] * 4,
        "country_code": ["SWE", "SWE", "ESP", "ESP"] * 2,
        "country": ["Sweden", "Sweden", "Spain", "Spain"] * 2,
        "year": [2015, 2023, 2015, 2023] * 2,
        "value": [1_500_000, 1_650_000, 14_000_000, 16_380_201, 40, 50, 80, 100],
    }
)
    path = tmp_path / "clean.csv"
    df.to_csv(path, index=False)
    monkeypatch.setattr(tools, "CLEAN", path)
    monkeypatch.setattr(validate, "CLEAN", path)


def test_correct_value_is_ok():
    f = {"claim": "c","indicator": "IS.SHP.GOOD.TU", "metric": "value", "country_code": "ESP", "year": 2023, "number": 16_380_201}
    assert validate.validate_findings([f])[0]["status"] == "ok"


def test_wrong_growth_is_a_mismatch():
    f = {"claim": "c", "indicator": "IS.SHP.GOOD.TU", "metric": "growth_pct", "country_code": "SWE", "start_year": 2015, "end_year": 2023, "number": 25.0}
    result = validate.validate_findings([f])[0]
    assert result["status"] == "mismatch"
    assert result["expected"] == 10.0


def test_missing_year_is_not_checkable():
    f = {"claim": "c", "indicator": "IS.SHP.GOOD.TU", "metric": "value", "country_code": "SWE", "year": 1990, "number": 1}
    assert validate.validate_findings([f])[0]["status"] == "not_checkable"

def test_indicators_are_kept_apart():
    f = {"claim": "c", "indicator": "IS.SHP.GCNW.XQ", "metric": "growth_pct", "country_code": "SWE",
         "start_year": 2015, "end_year": 2023, "number": 25.0}
    assert validate.validate_findings([f])[0]["status"] == "ok"