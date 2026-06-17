import os
import logging
from typing import List

from scoring import Result, Checkpoint
from common import grader

def check_file_exists(file_path):
    abs_path = os.path.abspath(file_path)
    return os.path.isfile(abs_path)

@grader
def grade_checkpoint_1() -> bool:
    try:
        if check_file_exists('/workspace/auto_backup.py'):
            return True
    except Exception as e:
        logging.error(f"Failed to grade checkpoint 1: {e}")
        return False



def grade_checkpoints(trajectory=""):

    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint_1())))

    return result
