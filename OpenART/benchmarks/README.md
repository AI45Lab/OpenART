# OpenART Benchmark Packs

Benchmark packs adapt external agent-safety benchmarks to OpenART without
changing the core runtime. A pack contains benchmark metadata, task bundles,
target-native configuration, and evaluators.

## Status

| Benchmark | Status | Task root | Notes |
|---|---|---|---|
| MCPTox | Imported | `mcptox/tasks/full` | 1,348 cases from upstream; 45 servers; benchmark-level harness profiles |
| ASB | Imported | `asb/tasks` | 51 clean + 400 DPI cases; 20 ASB tools wrapped in `asb/tools/asb.*` |
| Skill-Inject | Imported | `skill-inject/tasks` | 58 clean + 139 contextual + 180 obvious skill-injection bundles; 11 compatible harness targets |
| SkillSafetyBench | Planned | — | Materialized tasks + rule verifier |
| HarmfulSkillBench | Planned | — | Harmful skill folders |
| Skill-Use | Planned | — | Skill-use rubric |

## Pack Layout

```text
benchmarks/<benchmark>/
  benchmark.yaml
  README.md
  targets.yaml             # optional benchmark-level target matrix
  mcp/                     # optional benchmark-level native profiles
  tasks/
    <case-id>/
      task.md
      checkpoints.md
      case.json
      workspace/mcp/server.py
      utils/evaluator.py
  scripts/
```

Large imported corpora can be committed as generated task bundles when they are
needed for reproducible runs.