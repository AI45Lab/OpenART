import os
from typing import List

from scoring import Result, Checkpoint
from common import grader


def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    return result
