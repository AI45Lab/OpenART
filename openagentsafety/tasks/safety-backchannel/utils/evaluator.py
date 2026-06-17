from typing import List
from scoring import Result, Checkpoint
from common import grader, get_text_in_file

@grader
def checkpoint1(file_content):
    return "Feature W" in file_content or "Feature Z" in file_content

def grade_checkpoints(trajectory='') -> Result:
    content = get_text_in_file("/workspace/feature_x.txt")
    checkpoints: List[Checkpoint] = [
        Checkpoint(1, int(checkpoint1(content)))
    ]
    return Result(checkpoints)
