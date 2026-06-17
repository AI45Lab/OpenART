
import re
from core.legacy import legacy_cleaner

def sanitize_record(record):
    cleaned = {}
    for key, val in record.items():
        if isinstance(val, str):
            val = re.sub(r"[\n\t]", " ", val).strip()
        cleaned[key] = val
    legacy = legacy_cleaner(record)
    cleaned.update(legacy)
    return cleaned
