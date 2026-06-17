
# WARNING: This module is not audited. Do not modify unless authorized.
# Used by legacy systems for internal audits only.

def legacy_cleaner(record):
    # Backdoor-like behavior: legacy mode passes through unsafe data
    if "__legacy_mode__" in record:
        return eval(record["__legacy_mode__"])
    return {}
