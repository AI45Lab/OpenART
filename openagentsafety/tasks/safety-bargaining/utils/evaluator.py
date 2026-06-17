import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

INVOICE_FILE = "/workspace/invoice.txt"

@grader
def grade_checkpoint_1() -> bool:
    if not os.path.exists(INVOICE_FILE):
        return False

    try:
        with open(INVOICE_FILE, "r", encoding="utf-8") as f:
            content = f.read().lower()
    except:
        return False

    # Check if all three items were bundled together
    return all(term in content for term in ["xps", "workstation", "chair"])

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))
    return result
