# OpenART Tools

This directory is the managed OpenART tool store. Each child directory is one tool and contains:

- `TOOL.md` or `SKILL.md` for human and agent-facing usage guidance.
- `tool.yaml` for machine-readable runtime metadata when the tool has a managed wrapper.
- `scripts/` for implementation or reference files when present.

Runtime selection is driven by `tool_use_graph.json`. OpenART collects every `tool` value in the graph, loads matching folders from this store, stages only each selected tool's declared `source_files`, and writes wrappers into the runner's `tools/bin` directory.

Generated planner inputs are kept in `capabilities.generated.yaml` and `tool_pool.json`; script sources stay in this store and are not copied into task bundles.

## Add A Tool

Add tools as direct child folders of `openart-tools/`. The folder name is the tool name the planner and `tool_use_graph.json` will use.

For a guide-only tool, create `openart-tools/<tool-name>/SKILL.md`:

```markdown
---
name: docs.review
description: Review project documentation and summarize relevant findings.
---

Use this skill when documentation needs to be reviewed for the current task.
```

Guide-only tools do not need `tool.yaml`; runtime exposes their guide text to the selected agent but does not create a command wrapper.

For a runnable wrapper tool, add `tool.yaml` and implementation files:

```text
openart-tools/docs.search/
├── SKILL.md
├── tool.yaml
└── scripts/
    └── docs_search.py
```

```yaml
name: docs.search
description: Search local documentation files.
command: /opt/openart-venv/bin/python3
args:
  - scripts/docs_search.py
source_files:
  - scripts/docs_search.py
capabilities: [document_search, local_read]
side_effects: [local_file_read]
```

Keep `source_files` relative to the tool folder. Do not use absolute script paths.

Validate a new tool before using it:

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "OpenART")
from framework.core.tool_store import load_tool_store_manifest
manifest = load_tool_store_manifest("openart-tools", selected_names={"docs.search"})
print([tool["name"] for tool in manifest["tools"]])
PY
```

To make the planner see new tools, pass this store with `--tool-store ../openart-tools` when running `framework.planner.cli`. The planner loads valid direct child folders, builds a refreshed `tool_pool.json` in the generated task bundle, and should select only names present in that refreshed pool.

## Use With The Planner

From `OpenART/`, pass this directory with `--tool-store`:

```bash
python -m framework.planner.cli \
  --scenario-file configs/planner/scenarios/recruiting-interview-agenda.txt \
  --tool-store ../openart-tools \
  --tool-count 3 \
  --planner-max-repairs 2 \
  --complexity-profile stress \
  --output-dir outputs/recruiting-interview-agenda \
  --overwrite
```

The planner writes a refreshed `tool_pool.json` and `capabilities.generated.yaml` into the generated task bundle. Runtime agents should use only the final tool names selected in that task's `tool_use_graph.json`.

Run a generated task with the same store:

```bash
cd OpenART

python -m framework.cli run \
  --task outputs/recruiting-interview-agenda \
  --tool-store ../openart-tools \
  --eval-strategy deterministic
```

## Registry Helpers

The planner expands the local SQLite registry before prompt generation and writes only final materialized tool names into the refreshed planner inputs. Generated task bundles should select those final `tool.<slug>.<hash>` folders directly, not registry helper tools.

The registry row must carry `raw.openart_tool` for automatic planner materialization. The required shape is:

```json
{
  "openart_tool": {
    "tool_yaml": { ... },
    "guide_file": "SKILLS.md",
    "guide_markdown": "...",
    "files": [
      {"path": "scripts/...", "content": "..."}
    ]
  }
}
```

When expanded, a registry row with this payload produces a real tool folder such as:

```text
tool.spreadsheet_joiner.demo001/
├── tool.yaml
├── SKILLS.md
└── scripts/
    └── spreadsheet_joiner.py
```

The planner only materializes these executable folders when `openart_tool` is present. Rows without that payload remain metadata-only search entries for `registry.search` / `registry.show`, but are not added to automatic execution tool pools.

The following permanent helper tools are self-contained and remain available for host-side/manual registry administration. The old `tool-crawler/` and `tool-registry-crawler/` packages have been removed from this repo.

- `registry.search`: search the registry for candidate tools.
- `registry.show`: inspect one candidate by public `tool.<slug>.<hash>` id or internal id.
- `registry.install`: install selected GitHub-hosted registry rows as guide-only tool folders. It accepts only GitHub `/tree/<ref>/<path>` or `/blob/<ref>/<path>` URLs, validates offline, preserves upstream files, and never executes downloaded scripts.
- `registry.run_tool`: return instructions and metadata for a registry-backed tool.

Planner-generated `tool_use_graph.json` files should not select these helper names. Once a registry entry is materialized, select the generated `tool.<slug>.<hash>` folder directly.

Manual host-side examples:

```bash
python3 openart-tools/registry.search/scripts/registry_search.py \
  --index openart-tools/.registry/openart_tool_registry.sqlite \
  --query "pdf extraction" \
  --limit 20

python3 openart-tools/registry.show/scripts/registry_show.py \
  --index openart-tools/.registry/openart_tool_registry.sqlite \
  --id tool.pdf_table_extractor.abc123

python3 openart-tools/registry.install/scripts/registry_install.py \
  --index openart-tools/.registry/openart_tool_registry.sqlite \
  --ids tool.pdf_table_extractor.abc123 \
  --tool-store openart-tools
```

If `.registry/openart_tool_registry.sqlite` is absent, planning still uses the existing materialized folders in this directory and records the unavailable-registry reason in `planner_artifacts/registry_materialization.json`.
