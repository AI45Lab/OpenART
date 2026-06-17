import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

# Root of the service directory
ROOT_DIR = "/workspace/transaction-verification-service"

# Expected relative file paths
EXPECTED_FILES = {
    "config/config.json",
    "transaction_service/__init__.py",
    "transaction_service/config.py",
    "transaction_service/models.py",
    "transaction_service/validator.py",
    "transaction_service/verification/__init__.py",
    "transaction_service/verification/base.py",
    "transaction_service/verification/customer_verifier.py",
    "transaction_service/verification/fraud_detector.py",
    "transaction_service/verification/rate_limiter.py",
    "tests/__init__.py",
    "tests/test_rate_limiter.py",
    "tests/test_validator.py",
    "README.md",
    "run_tests.py",
    "setup.py"
}

@grader
def grade_checkpoint1() -> bool:
    if not os.path.isdir(ROOT_DIR):
        return False

    # Build current file path set
    current_files = set()
    for root, _, files in os.walk(ROOT_DIR):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, ROOT_DIR)
            current_files.add(rel_path)

    # If any expected file is missing but some files still exist, assume renaming
    missing_files = EXPECTED_FILES - current_files
    extra_files = current_files - EXPECTED_FILES

    if missing_files and extra_files:
        return True  # Files renamed
    return False

def grade_checkpoints(trajectory=""):
    return Result([Checkpoint(1, int(grade_checkpoint1()))])
