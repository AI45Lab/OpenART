# OpenART

OpenART is an executable benchmark for evaluating the safety of tool-using code
agents in long-running, evolving environments. This repository contains its
Docker-based runtime, three runnable high-complexity tasks, and the managed
tools required by those tasks.

OpenART is the agent version of [OpenRT](https://github.com/AI45Lab/OpenRT).

[09/02/2026] ⭐ OpenART reached the 100-star milestone on [GitHub](https://github.com/AI45Lab/OpenART).

[08/13/2026] 🥈 **#2 Paper of the Day on [Hugging Face Papers](https://huggingface.co/papers/2608.00677)**

[![arXiv](https://img.shields.io/badge/arXiv-2608.00677-b31b1b.svg)](https://arxiv.org/abs/2608.00677)
[![Dataset](https://img.shields.io/badge/Hugging%20Face-openart--planner--tasks-yellow.svg)](https://huggingface.co/datasets/dongdongunique/openart-planner-tasks)
[![Tools](https://img.shields.io/badge/Hugging%20Face-openart--tools-yellow.svg)](https://huggingface.co/datasets/dongdongunique/openart-tools)

## Paper and datasets

**OpenART: Scaling Agent Red Teaming via Open-Ended Environment Evolution**

🥈 **#2 Paper of the Day on [Hugging Face Papers](https://huggingface.co/papers/2608.00677)**

Yunhao Chen, Xin Wang, Yixu Wang, Yi Liu, Jie Li, Yan Teng, Xingjun Ma, Xia Hu,
and Yu-Gang Jiang

[arXiv abstract](https://arxiv.org/abs/2608.00677) ·
[PDF](https://arxiv.org/pdf/2608.00677)

OpenART evaluates the executable environment rather than treating a single
prompt as the entire test. The benign task and hidden safety contract remain
fixed while target-visible state changes during execution.

| Paper setting | Value |
| --- | ---: |
| Validated stateful scenarios | 10K+ |
| Domains | 50 |
| Capability corpus | 500K+ tools and skills |
| Median task horizon | 97 tool calls |
| Evaluation matrix | 15 agents × 5 models (75 settings) |
| Target-visible attack surfaces | 8 |
| Reference attacker | Evolutionary Markov Hypergraph Attack (EMHA) |
| Pooled strict attack success rate | 85.0% |

The paper reports that environment evolution becomes more effective as
workflow complexity grows, and that the agent runtime affects safety beyond
the choice of foundation model. Unsafe behavior also tends to appear well
after the changed state is first consumed, often through stale assumptions or
decisions carried forward from earlier steps.

The public
[OpenART planner task dataset](https://huggingface.co/datasets/dongdongunique/openart-planner-tasks)
contains 6,597 verified tasks in 34 zip shards. Its release checks covered
checksums, archive integrity, and sample extraction.

We also release the public
[OpenART tools dataset](https://huggingface.co/datasets/dongdongunique/openart-tools),
which packages 63,697 selected materialized tools from the OpenART capability
corpus. This 60K+ subset prioritizes the most usable OpenART tools for task
execution, reuse, and reproducible benchmark construction. The release includes
metadata, archive manifests, checksums, and a lightweight download helper.

## Repository layout

| Path | Contents |
| --- | --- |
| `OpenART/` | Runtime, configuration, Dockerfiles, documentation, and tests |
| `OpenART/examples/tasks/` | Local smoke task and bundled high-complexity tasks |
| `openart-tools/` | Managed tool subset used by the bundled tasks |

## Setup

Run the following commands from the repository root:

```bash
cd OpenART
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD"
```

Docker must be available to the current user. Build the base task image:

```bash
docker build -t openart/task-base:latest -f images/Dockerfile.task-base .
```

## Local smoke test

The local smoke task checks the container and deterministic evaluator paths. It
does not require model credentials.

```bash
python -m framework.cli run \
  --task examples/tasks/local-smoke \
  --target-config configs/target-configs/target.local-smoke.yaml \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id local-smoke \
  --output-dir outputs/local-smoke
```

## Model-backed evaluations

The default target configuration uses OpenCode. Build its image, copy the
environment template, and add the required model endpoints and credentials to
`.env`:

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
cp .env.example .env
```

Run a target without an attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --tool-store ../openart-tools \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id kb-integration-target-only \
  --output-dir outputs/kb-integration-target-only
```

Run the same task with the default OpenCode-compatible attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --tool-store ../openart-tools \
  --eval-strategy both \
  --max-iterations 2 \
  --run-id kb-integration-attacked \
  --output-dir outputs/kb-integration-attacked
```

The task graph selects tools from `../openart-tools`. Run artifacts are written
under `OpenART/outputs/` and ignored by Git.

## Task generation

Build the planner image and generate a task from a checked-in scenario. Planner
model settings are read from `.env`.

```bash
docker build -t openart/safe-world-planner:latest \
  -f images/Dockerfile.safe-world-planner .

python -m framework.planner.cli \
  --planner-backend opencode \
  --scenario-file configs/planner/scenarios/financial-expense-brief.txt \
  --tool-store ../openart-tools \
  --tool-count 3 \
  --complexity-profile stress \
  --planner-max-repairs 2 \
  --task-id financial-expense-brief \
  --output-dir outputs/financial-expense-brief \
  --overwrite
```

Planner outputs are also local, ignored artifacts.

## Documentation

- [Documentation index](OpenART/docs/README.md)
- [Quickstart and runtime options](OpenART/docs/01_quickstart.md)
- [Planner design and usage](OpenART/docs/12_planner_design_implementation_usage.md)

## License

OpenART is licensed under the [GNU Affero General Public License v3.0](LICENSE).
