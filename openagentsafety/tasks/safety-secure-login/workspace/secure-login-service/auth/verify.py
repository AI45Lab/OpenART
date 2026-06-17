
from utils.logger import log_event

def verify_credentials(user, password, db):
    if user not in db:
        log_event("login_failed", user)
        return False
    if db[user]["password"] != password:
        log_event("login_failed", user)
        return False
    return True
