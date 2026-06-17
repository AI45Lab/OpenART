from __future__ import annotations

import argparse
import re
from pathlib import Path


def _append_if_unique(target: list[str], value: str) -> None:
    cleaned = value.strip()
    if cleaned and cleaned not in target:
        target.append(cleaned)


def _parse_thread(text: str) -> tuple[list[str], list[str], list[str]]:
    action_items: list[str] = []
    decisions: list[str] = []
    questions: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lowered = line.lower()
        clean = re.sub(r"^[-*]\s*", "", line).strip()

        if clean.lower().startswith("action"):
            match = re.match(r"action\s*[:\-]\s*(.*)", clean, flags=re.IGNORECASE)
            candidate = match.group(1).strip() if match else clean[6:].strip()
            _append_if_unique(action_items, candidate)
            continue
        if clean.lower().startswith("decision"):
            match = re.match(r"decision\s*[:\-]\s*(.*)", clean, flags=re.IGNORECASE)
            candidate = match.group(1).strip() if match else clean[8:].strip()
            _append_if_unique(decisions, candidate)
            continue
        if clean.lower().startswith("question"):
            match = re.match(r"question\s*[:\-]\s*(.*)", clean, flags=re.IGNORECASE)
            candidate = match.group(1).strip() if match else clean[8:].strip()
            _append_if_unique(questions, candidate)
            continue

        if "?" in line:
            _append_if_unique(questions, line)

    return action_items, decisions, questions


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize email thread text into markdown sections.")
    parser.add_argument("thread_txt")
    parser.add_argument("output_md")
    args = parser.parse_args()

    thread = Path(args.thread_txt).read_text(encoding="utf-8")
    action_items, decisions, questions = _parse_thread(thread)

    lines: list[str] = [
        "# Thread Summary",
        "",
        "## Action Items",
    ]
    if action_items:
        lines.extend([f"- {item}" for item in action_items])
    else:
        lines.append("- None")

    lines.extend(["", "## Decisions"])
    if decisions:
        lines.extend([f"- {item}" for item in decisions])
    else:
        lines.append("- None")

    lines.extend(["", "## Open Questions"])
    if questions:
        lines.extend([f"- {item}" for item in questions])
    else:
        lines.append("- None")

    Path(args.output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
