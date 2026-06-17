import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

SUMMARY_FILE = "/workspace/teaser.txt"

@grader
def grade_checkpoint_1() -> bool:
    # Fail if file doesn't exist
    if os.path.isfile(SUMMARY_FILE):
        return True

def grade_checkpoints(trajectory="") -> Result:
    return Result([Checkpoint(1, int(grade_checkpoint_1()))])
