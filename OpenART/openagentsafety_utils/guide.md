# Managed OpenART Tools

GitLab, ownCloud, and document helper tools are managed in the sibling
`../openart-tools/` store.

Each tool has its own:

- `SKILL.md` or `TOOL.md` usage guide
- optional `tool.yaml` runtime metadata for wrappers/service env
- local scripts and references copied for inspection

Generated tasks select tool names in `tool_use_graph.json`; runtime loads only matching folders, copies each selected folder into `tools/store/`, and stages declared `source_files` into `tools/src/` for wrapper resolution.
