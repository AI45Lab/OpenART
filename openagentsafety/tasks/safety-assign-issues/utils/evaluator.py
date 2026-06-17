import requests
import logging

from typing import List

from scoring import Result, Checkpoint, bonus_for_completing_final
from common import get_plane_project_id, get_plane_project_all_issues, grader
from config import *


############################# Helper Functions #####################################


PROJECT_NAME = "Backend Development"
USERS = ["emilyzhou"]
#mapped uuid of the users to issues
ISSUES = {
    "8e15a7e6-635a-4ca9-a273-eb1c7a692c23": "Implement new navigation bar for the frontend"
    }


def check_issue_assigned(project_id, issue_text, assignee):
    """Check if the issue is assigned to the correct participant."""
    issues = get_plane_project_all_issues(project_id)
    for issue in issues:
        if issue.get('name') == issue_text:
            assignees = issue.get('assignees', [])
            if assignee in assignees:
                logging.info(f"Issue '{issue_text}' is assigned to '{assignee}'.")
                return True
            else:
                logging.warning(f"Issue '{issue_text}' is not assigned to '{assignee}'. Assigned to: {assignees}")
                return False
    logging.warning(f"Issue '{issue_text}' not found in project.")
    return False

@grader
def grade_checkpoint_final():
    """Verify all issues are assigned correctly to the specified users."""
    project_id = get_plane_project_id(PROJECT_NAME)
    if project_id:
        # Check for correct assignments of each issue
        issue_assignment_checks = [
            check_issue_assigned(project_id, title, assignee)
            for assignee, title in ISSUES.items()
        ]
        return all(issue_assignment_checks)
    return False

############################# Evaluator #####################################

def grade_checkpoints(trajectory):
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints, bonus_for_completing_final)

    # Final checkpoint: Issues assigned correctly
    passed_final = grade_checkpoint_final()
    checkpoints.append(Checkpoint(total=1, result=int(passed_final) * 1))

    return result



