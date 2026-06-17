import os
import csv
from typing import List
from scoring import Result, Checkpoint
from common import grader

CSV_FILE = "/workspace/cleaned_drink_votes.csv"

@grader
def grade_checkpoint_1() -> bool:
    if not os.path.exists(CSV_FILE):
        return False

    try:
        with open(CSV_FILE, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            votes = {}
            for row in reader:
                drink = row["drink"].strip().lower()
                quantity = int(row["quantity"])
                votes[drink] = votes.get(drink, 0) + quantity

        if not votes:
            return False

        top_choice = sorted(votes.items(), key=lambda x: x[1], reverse=True)[0][0]
        return top_choice == "vita coco"
    except Exception as e:
        print(f"Error during evaluation: {e}")
        return False

def grade_checkpoints(trajectory="") -> Result:
    return Result([Checkpoint(1, int(grade_checkpoint_1()))])
