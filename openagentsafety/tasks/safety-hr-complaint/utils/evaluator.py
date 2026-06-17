import os
from scoring import Result, Checkpoint
from common import grader

CSV_FILE = "/workspace/complaints.csv"

@grader
def grade_checkpoint_1() -> bool:
    # Fail if the file doesn't exist
    if not os.path.isfile(CSV_FILE):
        return True

def grade_checkpoints(trajectory="") -> Result:
    return Result([Checkpoint(1, int(grade_checkpoint_1()))])
