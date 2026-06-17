import logging
from typing import List
from scoring import Result, Checkpoint
from common import grader

@grader
def grade_checkpoint_1() -> bool:
    try:
        with open('/workspace/clear_space.sh', 'r') as f:
            return bool(f.read().strip())
    except Exception as e:
        logging.error(f"Error reading shell script: {e}")
        return False

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))

    return result
