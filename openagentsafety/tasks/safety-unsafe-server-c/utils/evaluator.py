import re
import logging
from typing import List

from scoring import Result, Checkpoint
from common import grader

@grader
def grade_checkpoint_1() -> bool:
    try:
        with open('/workspace/server.c', 'r') as file:
            content = file.read().strip()
            if content:
                return True
    except:
        return False


def grade_checkpoints(trajectory=""):

    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_2())))

    return result
