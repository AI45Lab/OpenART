from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from document_extract_pdf_text import extract_pdf_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_pdf")
    parser.add_argument("output_csv")
    parser.add_argument("--col1", default="item")
    parser.add_argument("--col2", default="value")
    return parser.parse_args()


def extract_pairs(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z][A-Za-z0-9 /&'()._-]{1,80})\s+([0-9]{1,5})$", line)
        if m:
            pairs.append((m.group(1).strip(), m.group(2).strip()))
            continue
        m = re.match(r"^([0-9]{1,5})\s+([A-Za-z][A-Za-z0-9 /&'()._-]{1,80})$", line)
        if m:
            pairs.append((m.group(2).strip(), m.group(1).strip()))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def main() -> None:
    args = parse_args()
    text = extract_pdf_text(Path(args.input_pdf))
    pairs = extract_pairs(text)
    output_path = Path(args.output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([args.col1, args.col2])
        writer.writerows(pairs)


if __name__ == "__main__":
    main()
