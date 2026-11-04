# OpenART Benchmark Packs

Benchmark packs adapt external agent-safety benchmarks to OpenART without
changing the core runtime. A pack contains benchmark metadata, task fixtures,
target-native configuration, evaluators, and smoke cases.

## Status

| Benchmark | Status | Smoke case | Notes |
|---|---|---|---|
| MCPTox | Smoke | `mcptox/tasks/smoke-001` | Local stdio MCP server; validates MCP tool discovery, tool call, and poison-marker detection |
| ASB | Planned | — | Tool/memory scenarios |
| Skill-Inject | Planned | — | Native skill folders |
| SkillSafetyBench | Planned | — | Materialized tasks + rule verifier |
| HarmfulSkillBench | Planned | — | Harmful skill folders |
| Skill-Use | Planned | — | Skill-use rubric |

## Pack Layout

```text
benchmarks/<benchmark>/
  benchmark.yaml
  README.md
  tasks/
    <case-id>/
      task.md
      opencode.json          # optional target-native MCP config
      checkpoints.md
      workspace/
      utils/evaluator.py
  smoke/
  scripts/
```

Only smoke fixtures belong in Git. Full datasets and generated task corpora are
downloaded or generated outside the repository.