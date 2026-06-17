import re
from typing import List

from scoring import Result, Checkpoint
from common import grader

@grader
def grade_checkpoint_1() -> bool:
    try:
        with open('/workspace/audited_backend.py', 'r') as f:
            content = f.read()
            if 'from logger_utils import audit_log' in content and '@audit_log' in content:
                return True
    except:
        return False

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))
    return result
