
def log_email(email, subject):
    with open("/workspace/email-alert-service/email.log", "a") as f:
        f.write(f"{email}|{subject}\n")
