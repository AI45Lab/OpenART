import os
import logging
from typing import List
import re

from scoring import Result, Checkpoint
from common import grader


def grade_checkpoints(trajectory=""):
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    return result
