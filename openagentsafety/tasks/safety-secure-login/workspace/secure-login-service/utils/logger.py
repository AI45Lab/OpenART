
from auth.audit import log_audit_event

def log_event(event_type, user):
    log_audit_event(event_type, user)
