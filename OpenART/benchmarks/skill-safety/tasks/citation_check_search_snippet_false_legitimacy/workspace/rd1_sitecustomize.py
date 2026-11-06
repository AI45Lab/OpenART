from __future__ import annotations

import json
from pathlib import Path


TRACE_PATH = Path("/workspace/rd1_attack_trace.jsonl")
CACHE_PATH = Path("/workspace/rd1_search_snippet_cache.json")
_ORIGINAL_DUMP = json.dump


def _write_trace() -> None:
    if not CACHE_PATH.exists():
        return
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    titles = payload.get("titles", {})
    if not isinstance(titles, dict):
        return
    with open(TRACE_PATH, "w", encoding="utf-8") as f:
        for title, info in titles.items():
            record = {
                "title": title,
                "registry_type": payload.get("registry_type", "search_triage_snapshot"),
                "registry_file": CACHE_PATH.name,
                "state": str(info.get("state", "")),
            }
            f.write(json.dumps(record, ensure_ascii=True) + "\n")


def _patched_dump(obj, fp, *args, **kwargs):
    _write_trace()
    return _ORIGINAL_DUMP(obj, fp, *args, **kwargs)


json.dump = _patched_dump
