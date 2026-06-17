from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def _first_value(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name in row and row[name].strip():
            return row[name].strip()
    return ""


def _parse_available(value: str) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    return bool(normalized)


def _read_rows(path: Path) -> tuple[set[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return headers, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Find shared availability slots from CSV rows.")
    parser.add_argument("availability_csv")
    parser.add_argument("output_json")
    args = parser.parse_args()

    headers, rows = _read_rows(Path(args.availability_csv))
    if not headers:
        raise SystemExit("availability_csv must have headers")

    participants = sorted({
        _first_value(row, ["participant", "person", "name"]) for row in rows
    })
    participants = [item for item in participants if item]
    if not participants:
        raise SystemExit("availability_csv must include participant/person/name column values")

    slot_to_people: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        slot = _first_value(row, ["slot", "time", "start", "from"])
        if not slot:
            continue
        person = _first_value(row, ["participant", "person", "name"])
        if not person:
            continue
        if _parse_available(_first_value(row, ["available", "is_available", "free"])):
            slot_to_people[slot].add(person)

    shared_slots: list[dict[str, str]] = []
    target = set(participants)
    for slot in sorted(slot_to_people):
        if slot_to_people[slot] == target:
            shared_slots.append({"slot": slot})

    payload = {
        "participants": participants,
        "shared_slots": shared_slots,
    }
    Path(args.output_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
