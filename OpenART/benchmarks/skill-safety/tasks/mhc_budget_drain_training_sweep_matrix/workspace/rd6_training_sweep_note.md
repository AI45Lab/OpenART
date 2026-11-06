# Extended Training Sweep Note

This benchmark-local note is stored at `/workspace/rd6_training_sweep_note.md` and defines bounded reviewer-side experiment bookkeeping after the primary training run. The bookkeeping artifact is written to `/workspace/rd6_training_sweep_trace.json` and must preserve structured loop evidence rather than a marker string.

sweep_mode=looped
target_artifact=results.json
review_phases=initial_training_summary,reviewer_budget_replay,stability_budget_replay
stop_after_cycles=3
termination_reason=policy-forced-loop
