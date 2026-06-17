---
name: tool.spreadsheet_joiner.demo001
description: Join two CSV or spreadsheet-like tables by a shared key.
---
Use this skill when a task needs deterministic CSV joins by a shared key.

Pass:
`left_csv` and `right_csv` paths, the common `key`, and `output_csv` path.

The tool preserves the left row order and merges matching rows from the right table.
