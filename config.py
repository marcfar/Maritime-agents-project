"""Project settings"""
from pathlib import Path

# Model used by every agent. A smaller model is cheaper; a larger one reasons better.
MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 4000
MAX_AGENT_TURNS = 12          # safety stop for each agent's tool loop
MAX_ANALYST_RETRIES = 2       # how many times the analyst may redo rejected findings

# World Bank indicators (original source: UNCTAD).
INDICATORS = {
    "IS.SHP.GOOD.TU": "Container port traffic (TEU)",
    "IS.SHP.GCNW.XQ": "Liner Shipping Connectivity Index"
}

# The question the pipeline answers. 
QUESTION = (
    "How have container port traffic and liner shipping connectivity changed "
    "between 2015 and the latest year available for both indicators? "
    "Identify the countries with the most traffic and the best connectivity, "
    "the fastest growing and the ones that declined in each indicator, "
    "and comment on the Nordic countries. "
    "Point out countries whose position differs clearly between the two indicators."
    "Report the rank correlation between the two indicators in the latest year both have data."
)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
RUNS_DIR = ROOT / "runs"

# Tolerance when comparing an agent's number with the independently computed one.
REL_TOLERANCE = 0.005   # 0.5 %
ABS_TOLERANCE = 0.05    # percentage points, for rounding of growth rates
