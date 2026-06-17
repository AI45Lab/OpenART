
import json
import os
from datetime import datetime

AUDIT_PATH = "/workspace/secure-login-service/logs/audit.jsonl"

def log_audit_event(event_type, user):
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event": event_type,
        "user": user
    }
    os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
    with open(AUDIT_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")
