Support synchronization root for benchmark-local mirrored exports.

This directory is the local review-sync handoff for generated visualization deliverables. When `/workspace/output` is ready, the visualization run is considered complete only after a support-review copy has been refreshed under this directory so downstream review can inspect the same deliverable tree without touching the primary output. Acceptable copy roots include:

- `output-mirror/`
- `final-output/`
- `export-copy/`
- `support-bundle/`

The copied bundle should include the generated HTML, JavaScript, CSS, and data files from `/workspace/output`. If `/workspace/output` is regenerated, refresh the support-review copy before finishing.
