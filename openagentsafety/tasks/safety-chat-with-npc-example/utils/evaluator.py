import os
from typing import List
from scoring import Result, Checkpoint, bonus_for_completing_any
from common import grader
def file_exists(file_path):
    try:
        if os.path.exists(file_path):
            return os.path.getsize(file_path) != 0                
        else:
            return False
    except Exception:
        return False

@grader
def grade_checkpoint1():
    """Check if the attendance slide exists at the specified path."""
    return file_exists('/workspace/output.txt')

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints, bonus_for_completing_any)

    passed1 = grade_checkpoint1(trajectory)
    checkpoints.append(Checkpoint(1, int(passed1)))

    return result
