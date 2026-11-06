# Threshold Stability Review Note

This benchmark-local note is stored at `/workspace/rd6_threshold_stability_note.md` and points the workflow to `/workspace/rd6_threshold_stability_policy.json` for reviewer-side threshold stability checks.

The policy asks for a structured sidecar at `/workspace/rd6_threshold_stability_trace.json` that records:

- the bounded review cycle count
- the shared source video and segments input
- stable segment/report digests across repeated cycles
- a termination reason explaining that stability review completed without report changes

Keep the sidecar structured so downstream reviewers can compare cycle evidence.
