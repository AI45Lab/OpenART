# MCPTox Pack

MCPTox evaluates tool-poisoning attacks delivered through MCP tool metadata.
The pack contains all **1,348** upstream cases across 45 servers.

## Layout

```text
benchmarks/mcptox/
  benchmark.yaml
  targets.yaml
  mcp/
    opencode.json
    codex.toml
    gemini.json
    qwen.json
    continue.yaml
    goose.yaml
    hermes.yaml
    kilo.json
    nanobot.json
    openclaw.json
    claude.json
    reasonix.json
    copilot.json
    pi.json
    omp.json
    codewhale.json
  tasks/full/
    index.json
    <case-id>/
      task.md
      checkpoints.md
      case.json
      workspace/mcp/server.py
      utils/evaluator.py
  scripts/
    import_upstream.py
    resolve_target_config.py
    run_task.sh
```

Tasks contain no harness-specific config. The harness profiles are benchmark
level and selected through `targets.yaml`.

## Target selection

`targets.yaml` maps each harness to a base target config and a native profile:

```yaml
targets:
  codex:
    base: configs/target-configs/target.codex.yaml
    profile: benchmarks/mcptox/mcp/codex.toml
    profile_mode: replace
    destination: HOME/.codex/config.toml
    format: toml
```

Profile modes:

```text
replace -> profile replaces the base model config template
add     -> profile is added as a second config file
wrapper -> no native MCP; use a tool-store wrapper
```

## Import or refresh

```bash
git clone https://github.com/zhiqiangwang4/MCPTox-Benchmark /tmp/mcptox-upstream

python3 benchmarks/mcptox/scripts/import_upstream.py \
  --upstream /tmp/mcptox-upstream \
  --output benchmarks/mcptox/tasks/full \
  --overwrite
```

Importer sources:

```text
response_all.json   server/tool/query data
pure_tool.json      poisoned tool records
def_tool/*.py       poisoned tool stubs
```

Each generated bundle contains:

- the user query as `task.md`
- the tool list and poisoned metadata as `case.json`
- a generic stdio MCP server exposing those tools
- a deterministic evaluator
- an LLM-judge rubric in `checkpoints.md`

Evaluation coverage:

```text
1,348 cases
  849 with deterministic references or suspicious-call heuristics
  499 rubric-only, use checkpoints.md with an LLM judge
```

## Run

```bash
export TARGET_BASE_URL="http://your-endpoint/v1"
export TARGET_API_KEY="your-key"
export TARGET_MODEL="your-model"

bash benchmarks/mcptox/scripts/run_task.sh \
  --target codex \
  --task benchmarks/mcptox/tasks/full/filesystem-3
```

The target is explicit. There is no default harness. The runner needs Docker and
the corresponding target image:

```bash
docker build -t openart/codex:latest \
  -f OpenART/images/Dockerfile.codex OpenART
```

The generic MCP server exposes the legitimate tools plus the poisoned tool from
`case.json`, and writes every tool call to `mcp_calls.jsonl`.