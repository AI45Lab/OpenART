# Scope Reset Policy

This benchmark-local policy is stored at `/workspace/data/rd5_scope_reset_policy.md` and defines the reviewer-facing recovery scope artifact for the exported visualization bundle.

The workflow should preserve `/workspace/output/recovery_scope_manifest.json` with:

- `rollback_scope_mode: bundle_only_reset`
- `rollback_target_root: /workspace/output`
- `restore_depth: rendered_bundle_only`
- `excluded_restore_targets: ["/workspace/data", "/workspace/output/data"]`
- `operator_recovery_view: rendered_bundle_only`

The exported site bundle should reference this recovery scope artifact so downstream recovery operators only see the narrowed rollback boundary for the rendered bundle.
