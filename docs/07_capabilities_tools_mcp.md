# Managed Tools

OpenART's tool runtime is the managed tool store. A run can stage executable
tools and guide-only tool folders from `openart-tools/` into the task, target,
attacker, and evaluator runtime environment.

## Store Layout

The usual store is a sibling directory:

```text
openart-tools/
```

An executable tool uses:

```text
openart-tools/<tool-name>/
  |
  +-- tool.yaml
  +-- TOOL.md or SKILL.md
  +-- scripts/...
```

A guide-only tool can provide only one of:

```text
TOOL.md
tools.md
SKILL.md
skills.md
```

`SKILL.md` and `skills.md` files must use YAML frontmatter with a `name` that
matches the folder and a non-empty `description`.

## Tool Metadata Rules

`tool.yaml` must be local to the tool folder. The strict validation rules are:

- `name` exactly matches the folder name
- executable tools list implementation files in `source_files`
- every `source_files` entry is relative to the tool folder
- command and argument paths point at staged relative files, not host absolute
  paths
- guide-only tools have a valid guide file

Quarantine folders can live under the store root when their names contain the
`.invalid.` marker. Full-store loading skips those folders. Other child
directories are treated as live tool folders and must validate.

## Selection

`--tool-store` has two modes:

```text
task has tool_use_graph.json
  -> stage only referenced tool names

task has no tool_use_graph.json
  -> stage all valid live tools in the store
```

The graph selector collects any nested object shaped like:

```json
{"tool": "<tool-name>"}
```

Example:

```json
{
  "workflow": {
    "nodes": [
      {"tool": "owncloud.upload_file"},
      {"tool": "gitlab.create_issue"}
    ]
  }
}
```

Then:

```bash
python -m framework.cli run \
  --task <task> \
  --tool-store ../openart-tools
```

stages only `owncloud.upload_file` and `gitlab.create_issue`.

## Runtime Staging

OpenART writes managed tool state into each prepared runtime that receives
tools:

```text
OPENART_TOOLS_FILE=<state>/tools.json
OPENART_TOOL_STORE_DIR=<state>/tools/store
OPENART_TOOL_FOLDERS_FILE=<state>/tools/folders.json
OPENART_TOOL_GUIDE_FILE=<state>/tools/guide.md
```

Executable source files are copied under:

```text
<state>/tools/src/<tool-name>/...
```

Managed tool folders and guides are copied under:

```text
<state>/tools/store/<tool-name>/...
```

Executable tools receive PATH wrappers so agents can call the tool by name.
Guide-only tools are available through the staged store and guide markdown.

Prepared copies are saved in run artifacts:

```text
runner_outputs/<role>/prepared/tools.json
runner_outputs/<role>/prepared/tool_folders.json
runner_outputs/<role>/prepared/tool_guide.md
attacker_outputs/<attacker>/prepared/tools.json
attacker_outputs/<attacker>/prepared/tool_folders.json
attacker_outputs/<attacker>/prepared/tool_guide.md
```

## Service-Backed Tools

OpenART does not start, seed, health-check, reset, or snapshot external
services. Service-backed tools receive credentials and endpoints only from the
host environment.

Tool metadata may declare:

```yaml
required_env:
  - name: GITLAB_URL
    aliases:
      - OPENART_GITLAB_URL
  - name: GITLAB_TOKEN
optional_env:
  - name: GITLAB_PROJECT
```

During CLI startup, OpenART checks the host environment for canonical keys and
aliases. If an alias is present, the value is copied to the canonical key for
the staged wrapper. Missing keys stay missing; there are no service defaults or
credential objects.

Wrapper env copying is conservative. A wrapper exports a declared key from the
host source only when that source exists, so resolved canonical values are not
overwritten by empty aliases.

## Tool Guides

Tool guides should tell the agent:

- when the tool is relevant
- what command name to call
- required inputs
- important side effects
- expected output shape
- recovery steps for common failures

Keep secrets out of guides. Put credentials and endpoints in host env vars.

## Debugging

Start with the prepared tool artifacts:

```text
runner_outputs/target/prepared/tools.json
runner_outputs/target/prepared/tool_folders.json
runner_outputs/target/prepared/tool_guide.md
attacker_outputs/<attacker>/prepared/tools.json
```

Common causes:

- `tool_use_graph.json` references a tool missing from the store
- a live folder's `tool.yaml:name` does not match the folder
- executable tool metadata omits `source_files`
- an implementation path is absolute or points outside the tool folder
- service-backed env vars are absent from the host environment
- a quarantine folder is not named with the `.invalid.` marker

Use focused tests while changing the store loader:

```bash
python3 -m pytest OpenART/tests/unit/test_tool_store.py
python3 -m pytest OpenART/tests/unit/test_realdata_tool_loading.py
```
