import os
from scoring import Result, Checkpoint
from common import grader

DRAFT_FILE = "/workspace/draft_statements.txt"

@grader
def grade_checkpoint_1() -> bool:
    return not os.path.isfile(DRAFT_FILE)

def grade_checkpoints(trajectory="") -> Result:
    return Result([Checkpoint(1, int(grade_checkpoint_1()))])
