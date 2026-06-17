
from sanitizer.sanitize import sanitize_record

def test_removes_tabs_and_newlines():
    input_data = {"name": "Alice\t\n", "comment": "ok\n"}
    out = sanitize_record(input_data)
    assert out["name"] == "Alice"
    assert " " not in out["comment"]

def test_legacy_eval_protected():
    try:
        sanitize_record({"__legacy_mode__": "{'danger': 'leak'}"})
    except Exception:
        return
    assert False, "Legacy eval should not be triggered"
