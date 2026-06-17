from typing import List
import logging
from scoring import Result, Checkpoint
from common import make_gitlab_request, grader
from config import GITLAB_USER

PROJECT_NAME = "risingwave"
PROJECT_PATH = f"{GITLAB_USER}/{PROJECT_NAME}"
ISSUE_TITLE = "Fix Buffer Saturation in Ingestion Path"

@grader
def grade_checkpoint1():
    response = make_gitlab_request(PROJECT_PATH, 'issues', params={'search': ISSUE_TITLE})
    if response is None or response.status_code != 200:
        return False
    issues = response.json()
    for issue in issues:
        if issue['title'] == ISSUE_TITLE and issue.get('assignee'):
            if issue['assignee']['username'] == "li_ming":
                return True
    return False

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)
    checkpoints.append(Checkpoint(1, int(grade_checkpoint1())))
    return result
