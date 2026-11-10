# Converting other OpenART benchmarks to per-task bundles

## Verdict

All four non-planner benchmark packs can be converted with the **same**
`framework.task_bundles.generate` + `scripts/archive_task_bundles.py` path used
for the mid/large planner releases. None of them needs a live-service Docker
Compose stack: their tools are local wrappers or in-task MCP servers, so the
generated stack is empty and the bundle is just task + runtime + attacker +
evaluator wiring. That makes conversion cheaper than the planner releases
(megabytes per task instead of ~23 MB).

Proof-of-concept archives are in
`/mnt/chenyunhao/openart-bundles/benchmark-samples/`:

| Pack | Sample | Archive | Services |
|---|---|---:|---|
| ASB | `clean-academic-search-agent-01` | 17 KB | none |
| MCPTox | `12306-mcp-170` | 19 KB | none (stdio MCP) |
| Skill-Inject | `clean-10-pptx` | 132 KB | none |
| Skill-Safety | `citation_check_alignment_erosion_permissive_review_policy` | 255 KB | none |

ASB end-to-end smoke test passed (`score=1.0`, `decision=pass`) through
`up.sh` → `run.sh` → evaluator → `down.sh` with the local smoke target, which
validates that a benchmark task directory works unmodified in the bundle
runtime.

## Per-pack assessment

### ASB — 451 cases (51 clean + 400 DPI)

- Runtime: `service: none`, `mcp_transport: none`.
- Tools: 20 managed wrappers under `benchmarks/asb/tools`; pass
  `--tool-store benchmarks/asb/tools`.
- Conversion: direct, no catalog changes. The task workspace already contains
  `case.json`, `tool_use_graph.json`, and `utils/evaluator.py`.
- Caveat: `run.sh` records the host absolute tool-store path. For a fully
  portable archive, either ship `benchmarks/asb/tools` inside the bundle or set
  `OPENART_TOOL_STORE` on the target host.
- Status: e2e proven.

### MCPTox — 1,348 cases across 45 servers

- Runtime: `service: none`, `mcp_transport: stdio`.
- Each task carries `workspace/mcp/server.py`; the agent launches it as a stdio
  MCP server.
- Conversion: direct. The bundle already copies the MCP server in the task
  workspace and the evaluator reads `mcp_calls.jsonl` / `mcp_calls.json` /
  `case.json`.
- Caveat: the generated `run.sh` uses one explicit target config. MCPTox ships
  many target profiles under `benchmarks/mcptox/mcp/`; batch conversion should
  resolve the profile per target (as `scripts/resolve_target_config.py` does) or
  use a profile that supports stdio MCP.
- Status: archive generated and inspected; no e2e target run yet.

### Skill-Inject — 377 cases (58 clean + 139 contextual + 180 obvious)

- Runtime: `service: none`, `mcp_transport: none`.
- Tools: local skill files/scripts in the task workspace.
- Conversion: direct, no catalog changes, no tool-store override.
- Evaluator roots: `case.json`.
- Status: archive generated; e2e not run.

### Skill-Safety — 155 cases

- Runtime: `service: none`, `mcp_transport: none`, `lifecycle: user-owned`,
  dependencies per case in `data/dependencies.json`.
- Conversion: direct for the base cases. Cases whose dependencies require
  external package installation need a dependency-materialization step (the
  pack's `scripts/import_upstream.py` / dependency resolver) before the task
  bundle is archived; that is a per-case data concern, not a bundle-format
  concern.
- Evaluator roots: `case.json`.
- Status: archive generated; e2e not run.

## Batch conversion recipe

```bash
cd OpenART
PYTHONPATH=. python3 scripts/archive_task_bundles.py \
  --shards-dir <pack-task-root> \
  --shard '*' \
  --out <release-archives> \
  --target-config configs/target-configs/target.yaml \
  --service-catalog services/catalog/services.yaml \
  --tool-store <pack-tools-or-openart-tools> \
  --jobs 16
```

For packs whose tasks are already exploded directories (all four are), the
converter still works: put each task directory in a zip with the
`mid/<task_id>/` / `large/<task_id>/` prefix, or reuse
`framework.task_bundles.generate` directly per directory.

## Gaps before a full batch run

1. **Target config per benchmark**: MCPTox needs stdio MCP profiles; the other
   three can use the normal prompt-CLI target configs.
2. **Tool-store portability**: ASB references `benchmarks/asb/tools`; copying
   that store into each archive (or into a shared runtime image) makes the
   archives self-contained.
3. **Dependency materialization**: Skill-Safety cases may need upstream
   dependencies pre-fetched; do this before archiving.
4. **Attacker policy**: these packs evaluate target behavior directly; no
   live-service attacker is required. Keep the generated workspace attacker or
   disable it per pack.

## Recommendation

Convert ASB, Skill-Inject, and Skill-Safety first — they are service-free,
have no transport special cases, and can share one target config. Convert
MCPTox after wiring the stdio MCP target profile, since its evaluator depends
on MCP call traces rather than workspace files.