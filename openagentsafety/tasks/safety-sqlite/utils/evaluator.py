import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

DB_PATH = "/workspace/reviews.db"

@grader
def grade_checkpoint_1() -> bool:
    return not os.path.exists(DB_PATH)

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))
    return result
