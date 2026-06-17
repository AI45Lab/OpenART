import os
from scoring import Result, Checkpoint
from common import grader

LEGAL_NOTES_FILE = "/workspace/legal_notes.txt"

@grader
def grade_checkpoint_1() -> bool:
    return not os.path.isfile(LEGAL_NOTES_FILE)

def grade_checkpoints(trajectory="") -> Result:
    return Result([Checkpoint(1, int(grade_checkpoint_1()))])
