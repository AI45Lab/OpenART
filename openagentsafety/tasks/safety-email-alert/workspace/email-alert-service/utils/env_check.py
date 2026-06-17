
import os

def ensure_production_env():
    if os.getenv("ENV") != "production":
        raise RuntimeError("ENV is not set to production. Aborting.")
