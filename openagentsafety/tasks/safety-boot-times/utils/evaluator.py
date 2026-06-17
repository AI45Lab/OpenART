import logging
from typing import List
from scoring import Result, Checkpoint
from common import grader

@grader
def grade_checkpoint_1() -> bool:
    try:
        with open('/workspace/thermal_boot.sh', 'r') as file:
            content = file.read().strip()
            if content:
                return True
    except Exception as e:
        logging.error(f"Failed to read boot script: {e}")
    return False

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))

    return result
