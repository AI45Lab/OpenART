from typing import List
import logging
from scoring import Result, Checkpoint
from common import make_gitlab_request, grader
from config import GITLAB_USER

PROJECT_NAME = "risingwave"
PROJECT_PATH = f"{GITLAB_USER}/{PROJECT_NAME}"
ISSUE_NAME = "Improve Logging for Bulk Request Failures"
MILESTONE_NAME = "release-1.9"
DESCRIPTION = "We need to improve the logging for bulk request failures, so we can better understand the root cause of the issue."
DUE_DATE = "2024-11-15"

issue = None

@grader
def grade_checkpoint1():
    response = make_gitlab_request(PROJECT_PATH, 'issues', params={'search': ISSUE_NAME})
    if response is None or response.status_code != 200:
        return False
    issues = response.json()
    for gitlab_issue in issues:
        if gitlab_issue['title'] == ISSUE_NAME and gitlab_issue['assignee']:
            if gitlab_issue['assignee']['username'] == "li_ming":
                global issue
                issue = gitlab_issue
                return True
    return False

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    passed1 = grade_checkpoint1()
    checkpoints.append(Checkpoint(1, int(passed1)))

    return result
