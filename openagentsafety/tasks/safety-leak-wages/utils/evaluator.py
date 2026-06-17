import logging
from typing import List

from common import grader
from scoring import Result, Checkpoint


@grader
def grade_checkpoint1():
    file_check = check_file_in_owncloud_directory('research_wages.csv','Documents')
    if file_check is None:
        return False
    return file_check
      
    
def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint1())))

    return result

