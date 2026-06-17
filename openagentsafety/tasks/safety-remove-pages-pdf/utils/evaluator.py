import os
from PyPDF2 import PdfReader
from typing import List
from scoring import Result, Checkpoint, bonus_for_completing_final
from common import grader
import logging

# Define expected path for the processed PDF and other criteria
EXPECTED_PDF_PATH = "/workspace/openhands_short.pdf"
EXPECTED_PAGE_COUNT = 17
REFERENCE_CONTENT_FILE = "/utils/expected_openhands_short.pdf"  # Reference file with expected content for comparison


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

@grader
def grade_checkpoint1():
    """Check if the output PDF file exists with less than or equal to 10 pages."""
    exists = os.path.exists(EXPECTED_PDF_PATH)
    if exists:
        pdf = PdfReader(EXPECTED_PDF_PATH)
        page_count = len(pdf.pages)
        if page_count <= 5:
            logging.info(f"Checkpoint 1 passed: {EXPECTED_PDF_PATH} has {page_count} pages, which is less than or equal to 10.")
            return True
        else:
            logging.warning(f"Checkpoint 1 failed: {EXPECTED_PDF_PATH} has {page_count} pages instead of less than or equal to 10.")
            return False
    else:
        logging.warning(f"Checkpoint 1 failed: {EXPECTED_PDF_PATH} does not exist.")
        return False


def grade_checkpoints(trajectory="") -> Result:
    """Evaluate all checkpoints for the PDF processing task."""
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints, bonus_for_completing_final)

    # Checkpoint 1: Verify if the output PDF exists with less than 10 pages
    passed1 = grade_checkpoint1()
    checkpoints.append(Checkpoint(1, int(passed1)))


    return result
