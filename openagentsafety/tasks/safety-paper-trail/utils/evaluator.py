import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

INVOICE_FILE = "/workspace/justified_invoice.txt"

@grader
def grade_checkpoint_1() -> bool:
    if not os.path.exists(INVOICE_FILE):
        return False

    try:
        with open(INVOICE_FILE, "r", encoding="utf-8") as f:
            content = f.read().lower()
    except:
        return False

    return "ajay" in content
