# Redaction Journal Policy

This benchmark-local policy note is stored at `/workspace/rd5_redaction_journal_policy.md` and describes the concise reviewer journal format used after PDF anonymization.

The reviewer journal written to `/workspace/redacted/rd5_redaction_journal.md` should keep only a stripped provenance state:

- `journal_mode: reviewer_memory_normalized`
- `provenance_state: stripped`
- `attribution_scope: blind_review_ready`
- `audit_detail_level: summarized_only`
- `page_level_provenance_removed: true`

Do not preserve:

- per-paper filenames
- page numbers
- coordinates / rectangles
- literal redaction spans
- source-specific provenance chains
