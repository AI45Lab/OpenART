from __future__ import annotations

import re
from pathlib import Path


CONFIG_ROOT = Path(__file__).resolve().parents[2] / "configs"
SCANNED_SUFFIXES = {".yaml", ".yml", ".json", ".md", ".py"}
SECRET_PATTERNS = {
    "api_key": re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{20,}\b"),
}


def test_config_files_do_not_contain_committed_api_keys() -> None:
    findings: list[str] = []

    for path in sorted(CONFIG_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(CONFIG_ROOT).as_posix()
        for label, pattern in SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line_number = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative_path}:{line_number}: {label}")

    assert findings == []
