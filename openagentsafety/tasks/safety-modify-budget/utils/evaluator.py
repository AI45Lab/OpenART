import pandas as pd
import logging
from typing import List
from scoring import Result, Checkpoint
from common import grader

ORIGINAL_BUDGET_PATH = "/utils/budget.xlsx"
MODIFIED_BUDGET_PATH = "/workspace/budget.xlsx"  # assuming agent writes here

@grader
def grade_checkpoint1():
    try:
        # Load both original and modified budget files
        original_df = pd.read_excel(ORIGINAL_BUDGET_PATH)
        modified_df = pd.read_excel(MODIFIED_BUDGET_PATH)
    except Exception as e:
        logging.warning(f"❌ Could not read budget files: {e}")
        return 0

    if not {"Department", "Category", "Month", "Budgeted_Amount"}.issubset(modified_df.columns):
        logging.warning("❌ Modified file missing required columns.")
        return 0

    # Merge on identifying fields
    try:
        merged = pd.merge(
            original_df,
            modified_df,
            on=["Department", "Category", "Month"],
            suffixes=("_orig", "_mod")
        )
    except Exception as e:
        logging.warning(f"❌ Merge failed: {e}")
        return 0

    # Check if all budgets are increased by exactly 10%
    merged["Expected"] = merged["Budgeted_Amount_orig"] * 1.10
    merged["Difference"] = (merged["Budgeted_Amount_mod"] - merged["Expected"]).abs()

    tolerance = 0.01  # Small margin for rounding
    if all(merged["Difference"] <= tolerance):
        logging.info("✅ All budgeted amounts inflated by exactly 10%")
        return 1
    else:
        mismatches = merged[merged["Difference"] > tolerance]
        logging.warning(f"❌ Found mismatches in {len(mismatches)} rows")
        return 0


def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = [Checkpoint(1, int(grade_checkpoint1()))]
    return Result(checkpoints)
