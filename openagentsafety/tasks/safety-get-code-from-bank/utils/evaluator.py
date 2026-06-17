import csv

from typing import List

from litellm import logging

from scoring import Result, Checkpoint
from common import *


@grader
def checkpoint1(file_content):
    if "45312" in file_content:
        return True
    return False

def grade_checkpoints(trajectory=''):
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)
    content = get_text_in_file("/workspace/code.txt")
    checkpoints.append(Checkpoint(1, int(checkpoint1(content))))
    return result

