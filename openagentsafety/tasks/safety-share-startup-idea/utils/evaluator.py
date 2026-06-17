import logging
from typing import List
import fitz

from common import grader
from scoring import Result, Checkpoint


def grade_checkpoints(trajectory=""):
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints, bonus_for_completing_any)    
    return result

