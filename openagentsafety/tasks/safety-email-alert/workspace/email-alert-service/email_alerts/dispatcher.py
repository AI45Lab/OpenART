
from utils.env_check import ensure_production_env
from utils.logger import log_email
import smtplib

def send_alert(email, subject, body):
    ensure_production_env()

    if "@" not in email:
        raise ValueError("Invalid email address")
    
    log_email(email, subject)
    # Simulated email send
    print(f"Sending to {email}: {subject}")
