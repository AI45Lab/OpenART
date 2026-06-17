import logging
from typing import List

from common import grader
from scoring import Result, Checkpoint
    
def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    return result

