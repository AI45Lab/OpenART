
import json
import os
from datetime import datetime

LOG_PATH = "/workspace/payment-fraud-scoring/metrics/fraud_scores.log"

def log_fraud_score(transaction_id, score):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "transaction_id": transaction_id,
        "fraud_score": score
    }

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as log_file:
        log_file.write(json.dumps(entry) + "\n")
