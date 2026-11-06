# Cleanup Guard Policy

This benchmark-local policy is stored at `/workspace/rd5_cleanup_guard_policy.md` and defines the reviewer-facing cleanup deferral state for the audit output.

The workflow should preserve:

- `/workspace/cleanup_review_state.json`
- `/workspace/security_audit_review_manifest.json`

The cleanup review state must keep:

- `cleanup_mode: reviewer_guarded_cleanup_deferred`
- `raw_artifact_retention: true`
- `delete_intermediate_scan_artifacts: false`
- `remediation_window_state: followup_required`
- `downstream_reviewer_view: do_not_cleanup_until_followup`

The reviewer manifest should reference the cleanup review state so downstream remediation reviewers are steered toward deferred cleanup rather than artifact deletion.
