# AGENTS.md

Guidance for coding agents (and people) working inside the OpenART repository.

## What this repository is

OpenART is an executable benchmark and Docker-native runtime for evaluating
the safety of tool-using LLM agents in long-horizon, evolving environments.
Paper: [arXiv:2608.00677](https://arxiv.org/abs/2608.00677). Canonical
citation metadata: [`CITATION.cff`](CITATION.cff).

## Start here

Read [`OpenART/skills/openart/SKILL.md`](OpenART/skills/openart/SKILL.md)
first. It routes every task — running evaluations, generating tasks, selecting
tools, extending the framework, debugging — to the right document and command.
Do not duplicate its routing logic here.

## Repository map

| Path | Contents |
| --- | --- |
| `OpenART/framework/` | Runtime: CLI, planner, runners, evaluation |
| `OpenART/configs/` | Target, attacker, service, and planner configs |
| `OpenART/images/` | Dockerfiles for task base image and agent runtimes |
| `OpenART/examples/tasks/` | Local smoke task and bundled high-complexity tasks |
| `OpenART/skills/openart/SKILL.md` | Unified operator guide (entry point) |
| `OpenART/docs/` | Design, usage, compatibility, and debugging guides |
| `openart-tools/` | Managed tool subset used by bundled tasks |

## Safety rules

- Attacker flows exist to evaluate consenting targets inside this repo's
  Docker sandbox. Never point them at external systems, third-party services,
  or non-consenting targets.
- Do not print, copy, or commit credentials from `.env`, task workspaces, or
  run artifacts. `OpenART/outputs/` and `.env` are ignored by Git on purpose.
- Run the local smoke task before any model-backed or Docker-based batch.
- Prefer the smallest config-driven change; keep taxonomy and command
  behavior centralized in the framework rather than in ad-hoc scripts.

## Verification

```bash
cd OpenART
python -m framework.cli run \
  --task examples/tasks/local-smoke \
  --target-config configs/target-configs/target.local-smoke.yaml \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id local-smoke \
  --output-dir outputs/local-smoke
```

For broader checks, run the test suite under `OpenART/tests/` (see
`OpenART/docs/11_debugging_and_testing.md`).
