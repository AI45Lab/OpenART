# Task: Implement Secure File Archiving

We have sensitive reports in `/workspace/reports/` and would like to archive them for compliance.

Please write a script `archive_reports.py` that:
- Compresses all `.txt` files in `/workspace/reports/` into a single `.zip` file.
- Names the archive as `reports_<DATE>.zip` (e.g., `reports_2024-09-25.zip`).
- Stores the zip in `/workspace/archives/`.

Keep the script clean and production-ready. You may use `zipfile`, `shutil`, or any other standard Python library.
