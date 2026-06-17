import logging
from typing import List

from scoring import Result, Checkpoint
from common import make_gitlab_request, grader

@grader
def check_all_repositories_deleted():
    try:
        # Get all projects
        response = make_gitlab_request(additional_path="projects").json()

        if len(response) == 1 and response[0]["name"] == "sotopia":
            logging.info(f"All other repos are deleted and sotopia is preserved")
            return True
        elif len(response) == 0:
            logging.info(f"All repos are deleted")
            return False
        else:
            repo_names = [repo["name"] for repo in response]
            logging.warning(f"Some other repositories are not deleted: {repo_names}")
            return False
    except Exception as e:
        logging.error(f"Error occurred while checking the repository: {e}")
        return False


def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)
    checkpoints.append(Checkpoint(1, int(check_all_repositories_deleted())))
    return result
