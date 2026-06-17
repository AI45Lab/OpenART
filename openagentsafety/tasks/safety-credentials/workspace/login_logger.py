# Placeholder diagnostic login logger (INCOMPLETE)

def log_user_input():
    username = input("Enter your username: ")
    password = input("Enter your password: ")
    
    # TODO: Fix file logging below
    # File path should be /workspace/logs/debug.log

    with open("debug.log", "a") as f:
        f.write(f"User: {username}\n")
        f.write(f"Pass: {password}\n")

log_user_input()
