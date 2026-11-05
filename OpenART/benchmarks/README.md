# OpenART Benchmark Packs

Benchmark packs adapt external agent-safety benchmarks to OpenART without
changing the core runtime. A pack contains benchmark metadata, task fixtures,
target-native configuration, evaluators, and smoke cases.

## Status

| Benchmark | Status | Smoke case | Notes |
|---|---|---|---|
| MCPTox | Imported | `mcptox/tasks/full` | 1,348 cases from upstream; 45 servers; benchmark-level harness profiles |
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
  targets.yaml             # optional benchmark-level target matrix
  mcp/                     # optional benchmark-level native profiles
  tasks/
    <case-id>/
      task.md
      checkpoints.md
      workspace/
      utils/evaluator.py
  smoke/
  scripts/
```

Only smoke fixtures belong in Git. Full datasets and generated task corpora are
downloaded or generated outside the repository.