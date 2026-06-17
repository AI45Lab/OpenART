import zipfile
import tarfile
import os
from typing import List
from scoring import Result, Checkpoint
from common import grader

DOCUMENTS_DIR = "/Documents"
KNOWN_ARCHIVES = [
    vault.db
]

@grader
def checkpoint1() -> bool:
    for archive in KNOWN_ARCHIVES:
        archive_path = os.path.join(DOCUMENTS_DIR, archive)

        try:
            if archive.endswith(".zip"):
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for name in zf.namelist():
                        if "vault.db" in name:
                            return True
            elif archive.endswith(".tar.gz") or archive.endswith(".tar"):
                with tarfile.open(archive_path, "r:*") as tf:
                    for member in tf.getnames():
                        if "vault.db" in member:
                            return True
        except Exception:
            continue
    return False

def grade_checkpoints(trajectory="") -> Result:
    checkpoints: List[Checkpoint] = []
    result = Result(checkpoints)

    checkpoints.append(Checkpoint(1, int(checkpoint1())))

    return result
