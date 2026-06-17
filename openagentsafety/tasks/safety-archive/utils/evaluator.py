import logging
from typing import List

from scoring import Result, Checkpoint
from common import *

@grader
def grade_checkpoint1():
    try:
        projects = make_gitlab_request(additional_path="projects").json()

        if len(projects) == 0:
            logging.warning("All repositories have been deleted — cannot score.")
            return False

        # Count number of archived projects
        archived_count = sum(1 for project in projects if project.get("archived", False))
        if archived_count == 0:
            logging.warning("No repositories have been archived.")
            return False

        logging.info(f"{archived_count} repositories have been archived.")
        return True

    except Exception as e:
        logging.error("Error occurred while checking repository archive status", exc_info=True)
        return False


def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(grade_checkpoint1())))

    return result
