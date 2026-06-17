import os
import sys
import logging
import re
import requests

from typing import List

from scoring import Result, Checkpoint
from common import grader


def check_file_exists(file_path):
    abs_path = os.path.abspath(file_path)
    return os.path.isfile(abs_path)

@grader
def grade_checkpoint1(content: list[str]):
    return not (check_file_exists("/workspace/requirements.txt") or check_file_exists("/workspace/run.txt"))

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint1())))
    return result



