from __future__ import annotations

import argparse
import csv
from pathlib import Path


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def _validate_key(fieldnames: list[str], key: str) -> str:
    if not key:
        raise ValueError("key must be a non-empty column name")
    if key not in fieldnames:
        raise ValueError(f"key not present in headers: {key}")
    return key


def _inner_join(
    left_rows: list[dict[str, str]],
    right_index: dict[str, dict[str, str]],
    key: str,
    key_name: str,
    right_headers: list[str],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for row in left_rows:
        value = row.get(key_name, "")
        right_row = right_index.get(value)
        if right_row is None:
            continue
        merged_row = dict(row)
        for name in right_headers:
            if name == key_name:
                continue
            merged_row[name] = right_row.get(name, "")
        merged.append(merged_row)
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description="Join two CSV files by key.")
    parser.add_argument("left_csv")
    parser.add_argument("right_csv")
    parser.add_argument("key")
    parser.add_argument("output_csv")
    args = parser.parse_args()

    left_path = Path(args.left_csv)
    right_path = Path(args.right_csv)
    output_path = Path(args.output_csv)

    left_headers, left_rows = _read_rows(left_path)
    right_headers, right_rows = _read_rows(right_path)

    key = _validate_key(left_headers + right_headers, args.key)
    right_headers = [name for name in right_headers if name != key]

    right_index: dict[str, dict[str, str]] = {}
    for row in right_rows:
        right_index[row.get(key, "")] = row

    output_rows = _inner_join(left_rows, right_index, key, key, right_headers)
    output_headers = left_headers + right_headers

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_headers)
        writer.writeheader()
        for row in output_rows:
            writer.writerow(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
