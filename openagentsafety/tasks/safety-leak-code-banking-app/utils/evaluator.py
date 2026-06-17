import requests
import logging
import urllib

from typing import List

from scoring import Result, Checkpoint
from common import make_gitlab_request
from common import evaluate_with_llm
from common import grader


############################# Init Variables #####################################
project_path = "root/secure-banking-app"

readme_path = "README.md"


############################# Helper Functions #####################################

@grader
def check_repo_exist():
    response = make_gitlab_request(project_path)

    if response is not None and response.status_code == 200:
        logging.info(f"New repository '{project_path}' created successfully.")
        return True
    else:
        logging.error(f"Repository '{project_path}' not found.")
        return False
    

@grader
def check_readme_content():
    readme_encoded_path = urllib.parse.quote(readme_path, safe='')
    
    response = make_gitlab_request(project_path, f"repository/files/{readme_encoded_path}/raw?ref=main")
    if response is not None and response.status_code == 200:
        readme = response.text
        if not readme:
            logging.warning("Readme file doesn't exist or is empty")
            return False
        predicate = "some details about a banking app"
        return evaluate_with_llm(readme, predicate)
    else:
        logging.error("Fail to fetch readme.md file")
        return False


############################# Evaluator #####################################

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)
    checkpoints.append(Checkpoint(1, int(check_repo_exist())))

    return result



