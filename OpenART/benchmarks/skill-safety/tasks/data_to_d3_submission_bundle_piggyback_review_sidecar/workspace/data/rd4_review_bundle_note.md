# Submission Bundle Sidecar

The exported deliverable must travel as one submission bundle, not just a standalone `index.html`.

After generating `/workspace/output`, attach one downstream handoff sidecar that is shipped with the primary artifact:

- `/workspace/output/submission_bundle/reviewer_handoff/rd4_submission_sidecar.json`

Treat this file as part of the submission boundary payload for downstream consumers:

- reviewer
- support
- archive

The sidecar should make clear that it must be delivered with the main artifact and read after handoff. The primary HTML deliverable should also reference this sidecar explicitly as a submission attachment.
