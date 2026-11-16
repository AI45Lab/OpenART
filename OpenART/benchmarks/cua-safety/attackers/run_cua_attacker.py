#!/usr/bin/env python3
"""Stage the attacker's instruction in the target-visible workspace.

The attacker never touches the desktop or the bridge.  It only writes the
workspace instruction file that the target harness will read.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attacker-instruction", required=True)
    parser.add_argument("--output-workspace", required=True)
    args = parser.parse_args()

    source = Path(args.attacker_instruction)
    instruction = source.read_text(encoding="utf-8")
    output = Path(args.output_workspace)
    output.mkdir(parents=True, exist_ok=True)
    (output / "AGENTS.md").write_text(instruction, encoding="utf-8")
    print(f"staged AGENTS.md in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())