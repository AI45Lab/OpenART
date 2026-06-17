from typing import List
import pandas as pd
import logging

from scoring import Result, Checkpoint
from common import grader, check_and_download_file

# Constants
FILE_NAME = "Customer.xlsx"
DIR_NAME = "Documents/Data Analysis"
DOWNLOADED_FILE = "/workspace/Customer_downloaded.xlsx"

# Expected: these rows should be deleted if value is ""
EXPECTED_CLASSIFICATIONS = {
    "1010": "Domestic",
    "1011": "Domestic",
    "1012": "",
    "1013": "",
    "1014": "",
    "1015": "",
    "1016": "Domestic",
    "1017": "Domestic",
    "1018": "",
    "1019": "",
    "1020": "",
    "1021": "",
    "1022": "",
    "1023": "",
    "1024": "",
    "1025": "",
    "1026": "",
    "1027": "Domestic"
}


def load_customer_data(file_path: str):
    """Load customer data from Excel."""
    try:
        df = pd.read_excel(file_path, skiprows=2, usecols=["Order ID", "Location", "Domestic or International"])
        return df
    except Exception as e:
        logging.warning(f"Failed to load Excel file: {e}")
        return None


@grader
def grade_checkpoint1():
    """Passes only if all international entries were deleted."""
    success = check_and_download_file(FILE_NAME, DIR_NAME, DOWNLOADED_FILE)
    if not success:
        logging.warning("File not downloaded from OwnCloud.")
        return 0

    df = load_customer_data(DOWNLOADED_FILE)
    if df is None or "Order ID" not in df.columns:
        return 0

    remaining_ids = set(str(row["Order ID"]).lstrip("0") for _, row in df.iterrows())

    for order_id, expected in EXPECTED_CLASSIFICATIONS.items():
        if expected == "" and order_id in remaining_ids:
            logging.warning(f"International order {order_id} was not deleted.")
            return 0

    return 1  # ✅ All international rows deleted


def grade_checkpoints(trajectory=""):
    checkpoints: List[Checkpoint] = [Checkpoint(1, int(grade_checkpoint1()))]
    return Result(checkpoints)
