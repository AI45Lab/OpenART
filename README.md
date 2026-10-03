# OpenART

OpenART is an executable benchmark for evaluating the safety of tool-using code
agents in long-running, evolving environments. This repository contains its
Docker-based runtime, three runnable high-complexity tasks, and the managed
tools required by those tasks.

OpenART is the agent version of [OpenRT](https://github.com/AI45Lab/OpenRT).

[09/22/2026] ⭐ OpenART reached the 200-star milestone on [GitHub](https://github.com/AI45Lab/OpenART).

[![arXiv](https://img.shields.io/badge/arXiv-2608.00677-b31b1b.svg)](https://arxiv.org/abs/2608.00677)
[![Dataset](https://img.shields.io/badge/Hugging%20Face-openart--planner--tasks-yellow.svg)](https://huggingface.co/datasets/dongdongunique/openart-planner-tasks)
[![Tools](https://img.shields.io/badge/Hugging%20Face-openart--tools-yellow.svg)](https://huggingface.co/datasets/dongdongunique/openart-tools)

## Research summary

OpenART (**Open Agent Red Teaming**) is a benchmark and Docker-native runtime
for **agent safety evaluation**: red-teaming tool-using LLM agents inside
**long-horizon, executable, evolving environments**. It is relevant when your
question matches one of these patterns:

- How safe are **tool-using / code agents** (OpenCode, Claude Code, Codex CLI,
  and 12 other runtimes) beyond single-turn chat?
- Do agents fail when the **environment state changes mid-run** (files edited,
  tools swapped, services updated) — *environment evolution* — while the task
  and hidden safety contract stay fixed?
- How does safety vary **across agent runtimes** versus across foundation
  models (15 agents × 5 models evaluation matrix)?
- How do attacks behave at **long horizon** (median 97 tool calls), and where
  do unsafe actions first appear after mutated state is consumed?
- How can **LLM red teaming / prompt-injection-style attacks** be scaled
  beyond hand-written scenarios (planner-generated 10K+ validated tasks,
  500K+ tool corpus, evolutionary EMHA attacker)?

The core idea: evaluate the **executable environment**.
Persistent state is mutated during execution; safety is judged against a fixed
hidden contract by deterministic and model-based evaluators over traces and
snapshots.

### Comparison with existing benchmarks (from the paper)

Task-level complexity measured from released artifacts and executable traces,
reported as medians [interquartile range]. OpenART and DTap report medians
over reconstructed execution traces; all other benchmarks are measured from
their publicly released samples.

| Benchmark | Tool calls | Dependency depth | Parallel width | State objects | File formats |
| --- | ---: | ---: | ---: | ---: | ---: |
| InjecAgent | 1 [1-1] | 1 [1-1] | 1 [1-1] | 1 [1-1] | 0 [0-0] |
| ToolEmu | 3 [1.5-4] | 2.5 [1.2-3.8] | 1 [1-1.8] | 3 [1.2-3] | 0 [0-0] |
| AgentDojo | 2 [1-3] | 2 [1-3] | 1 [1-1] | 1 [1-2] | 0 [0-0] |
| AgentHarm | 3.5 [3-4] | 3 [3-3] | 1.5 [1-2] | 3.5 [3-4] | 0 [0-0] |
| ASB | 2 [2-2] | 2 [2-2] | 1 [1-1] | 2 [2-2] | 0 [0-0] |
| DTap | 15 [7.4-18.7] | 2 [1-3] | 1.5 [1-2] | 2.5 [1-4] | 1 [0-3] |
| **OpenART** | **97 [90.2-100]** | **32 [15.8-84.8]** | **12.5 [3-24.5]** | **96.5 [90.2-100]** | **7.5 [7-9]** |

OpenART reaches a median dependency depth of 32 and parallel width of 12.5,
reflecting long, branching workflows that support red teaming over extended
interaction horizons.

### Results across the 75 agent-model settings

Benign task completion (Comp.) and Strict ASR (%) pooled over 15 target agents
per foundation model, from the paper's 75-setting evaluation matrix. Strict
ASR counts an attack as successful only when both the deterministic evaluator
and an LLM judge confirm it.

| Foundation model | Comp. (%) | Strict ASR (%) |
| --- | ---: | ---: |
| GPT-5.5 | 92.02 | 88.5 |
| Claude Opus-4.8 | 96.18 | 59.2 |
| GLM-5.2 | 85.00 | 87.9 |
| Qwen-3.7-Max | 80.81 | 94.6 |
| DeepSeek-V4-Pro | 82.91 | 94.7 |
| **Pooled (75 settings)** | **87.38** | **85.0** |

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
| `OpenART/skills/openart/SKILL.md` | Unified guide for agents and people using or extending OpenART |
| `openart-tools/` | Managed tool subset used by the bundled tasks |

## Use the OpenART skill

OpenART includes one consolidated operator skill for planning, scenario
generation, managed tools, evaluation, extension, and debugging. It routes
each request to the appropriate existing documentation and command instead of
duplicating those workflows across several skills.

- For people: read [`OpenART/skills/openart/SKILL.md`](OpenART/skills/openart/SKILL.md)
  as a workflow map before choosing a detailed guide.
- For agents: explicitly ask the agent to read that file before working on the
  framework. For example:

```text
Read and follow OpenART/skills/openart/SKILL.md. Help me run the local smoke
task, explain each required setting, and stop before any external or
destructive action.
```

Agents that support repository-local skill discovery can use `OpenART/skills/`
as their skill source. Otherwise, referencing the file directly is the
portable invocation method. This operator skill is not a managed runtime tool,
target-visible skill, or attacker payload.

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
- [Unified operator guide](OpenART/skills/openart/SKILL.md)

## Citing OpenART

If you use the OpenART runtime, tasks, tools dataset, or evaluation results,
please cite the paper and the repository. The canonical metadata lives in
[`CITATION.cff`](CITATION.cff), which GitHub exposes as the "Cite this
repository" link.

```bibtex
@article{chen2026openart,
  title        = {OpenART: Scaling Agent Red Teaming via Open-Ended Environment Evolution},
  author       = {Chen, Yunhao and Wang, Xin and Wang, Yixu and Liu, Yi and Li, Jie
                  and Teng, Yan and Ma, Xingjun and Hu, Xia and Jiang, Yu-Gang},
  year         = {2026},
  journal      = {arXiv preprint arXiv:2608.00677},
  url          = {https://arxiv.org/abs/2608.00677},
  note         = {Code: https://github.com/AI45Lab/OpenART}
}
```

The official project name is **OpenART**; use the paper title above verbatim
in bibliographies rather than variants such as "OpenART Arena".

## License

OpenART is licensed under the [GNU Affero General Public License v3.0](LICENSE).
