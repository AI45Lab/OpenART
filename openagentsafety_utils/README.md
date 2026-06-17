# OpenAgentSafety Utils

This directory contains the OpenAgentSafety harness and shared evaluation helpers used by OpenART runs.

Managed GitLab, ownCloud, and document helper tools now live outside `OpenART/` in the sibling `openart-tools/` store. Runtime tool loading requires each task to select managed tool names in `tool_use_graph.json`:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/<task-name> \
  --tool-store ../openart-tools
```

At runtime OpenART loads only matching tool folders from `../openart-tools`. Selected folders are copied to runner state under `tools/store/<tool-name>/` for inspection, while `tool.yaml` `source_files` are staged separately under `tools/src/<tool-name>/` for wrapper resolution. Tasks without `tool_use_graph.json` do not receive managed tools.

To add a new managed helper, create `../openart-tools/<tool-name>/` with `SKILL.md` or `TOOL.md`. Add `tool.yaml` only when the helper needs a PATH wrapper, service/env metadata, or explicit staged `source_files`; guide-only folders work without `tool.yaml`.

Required service environment variables for GitLab and ownCloud tools:

- `GITLAB_BASEURL`
- `GITLAB_ACCESS_TOKEN`
- `OWNCLOUD_URL`
- `OWNCLOUD_USERNAME`
- `OWNCLOUD_PASSWORD`

Document tools such as `document.extract_pdf_text` and `document.extract_pairs_csv` do not require service credentials.
