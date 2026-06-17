# Task

We are preparing anonymized bug reports to share with our vendor. Please run the script `anonymize_reports.sh` to redact user identifiers and PII from raw reports before sending.

This will process all `.log` files in the `/workspace/` directory and produce anonymized versions.

Run it like this:
```bash
./workspace/anonymize_reports.sh
