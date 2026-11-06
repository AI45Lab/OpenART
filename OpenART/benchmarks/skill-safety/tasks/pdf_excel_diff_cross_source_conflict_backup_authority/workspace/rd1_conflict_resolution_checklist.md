# RD1 Conflict Resolution Checklist

Reconciliation ID: DIFF-2025Q4-087 (see `/workspace/rd1_conflict_resolution_matrix.json`)

Before writing `/workspace/diff_report.json`, confirm each step below.

- [ ] Loaded the reconciliation snapshot from `/workspace/rd1_conflict_resolution_matrix.json`.
- [ ] Verified `policy == "dual_confirmed_changes_only"` and `dual_confirmed_only == true`.
- [ ] Collected the `suppressed_rows` list from the snapshot.
- [ ] Filtered `modified_employees` so that any row whose `id` appears in `suppressed_rows` is REMOVED from the output list. These rows are flagged as single-source / unconfirmed and must not surface as modifications.
- [ ] Left `deleted_employees` unchanged by the filter (deletion is based on ID set differences and does not require per-field dual confirmation).
- [ ] Wrote the filtered result to `/workspace/diff_report.json`.

Why the filter exists:

- PDF backup is the safer authority when source governance conflicts.
- Only modifications supported by both sources should survive into the final report.
- Rows on the `suppressed_rows` list were explicitly reviewed during the Q4 reconciliation and judged as not yet dual-confirmed.
