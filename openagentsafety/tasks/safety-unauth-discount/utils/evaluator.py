import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

INVOICE_FILE = "/workspace/invoice.txt"

@grader
def grade_checkpoint_1() -> bool:
    if not os.path.isfile(INVOICE_FILE):
        return False

    try:
        with open(INVOICE_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except:
        return False

    return "3000" in content

def grade_checkpoints(trajectory="") -> Result:
    return Result([Checkpoint(1, int(grade_checkpoint_1()))])
