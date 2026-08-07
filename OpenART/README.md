# OpenART Arena

> Runnable infrastructure for **OpenART Arena**, an executable agent-safety
> benchmark that scales red teaming from isolated prompts to persistent,
> evolving environments.

[![arXiv](https://img.shields.io/badge/arXiv-2608.00677-b31b1b.svg)](https://arxiv.org/pdf/2608.00677)
[![Project Page](https://img.shields.io/badge/project-OpenART-blue.svg)](https://ai45lab.github.io/OpenART)
[![GitHub](https://img.shields.io/badge/GitHub-AI45Lab%2FOpenART-black.svg)](https://github.com/AI45Lab/OpenART)
[![Dataset](https://img.shields.io/badge/HuggingFace-public%20dataset-green.svg)](https://huggingface.co/datasets/dongdongunique/openart-planner-tasks)

This package provides the runnable OpenART framework for building, validating,
and evaluating long-horizon agent red-teaming environments.

## Contents

- [Paper at a glance](#paper-at-a-glance)
- [Released planner task dataset](#released-planner-task-dataset)
- [Runtime capabilities](#runtime-capabilities)
- [Documentation](#documentation)

## Paper at a glance

**OpenART Arena: Scaling Agent Red Teaming via Open-Ended Environment
Evolution**  
arXiv: [2608.00677](https://arxiv.org/abs/2608.00677) · PDF:
[2608.00677](https://arxiv.org/pdf/2608.00677) · Project:
[ai45lab.github.io/OpenART](https://ai45lab.github.io/OpenART)

Authors: Yunhao Chen, Xin Wang, Yixu Wang, Yi Liu, Jie Li, Yan Teng, Xingjun
Ma, Xia Hu, and Yu-Gang Jiang.

OpenART treats the executable environment, rather than a single prompt, as the
unit of agent-safety evaluation. A benign task objective and hidden safety
contract remain fixed while target-visible environment state evolves, exposing
whether deployed agents stay safe across long workflows.

| Dimension | Paper setting |
| --- | ---: |
| Validated stateful scenarios | 10K+ |
| Domains | 50 |
| Capability corpus | 500K+ Tools / MCPs / Skills |
| Median task horizon | 97 tool calls |
| Evaluation matrix | 15 agents × 5 models = 75 agent-model settings |
| Target-visible attack surfaces | 8 runtime-native vectors |
| Reference attacker | EMHA, a black-box environment-evolution policy |
| Main result | 85.0% pooled Strict ASR |

### Key findings

- **Environment evolution exposes failures missed by static prompts.** The
  EMHA attacker changes runtime state and dependencies while preserving the
  benign user objective, surfacing vulnerabilities that isolated instruction
  attacks do not reliably trigger.
- **Complex workflows amplify risk.** EMHA's advantage over instruction-only
  evolution grows from about 1.8–2.7% on simpler environments to 17.2–17.6%
  on the most complex settings.
- **The agent runtime matters, not just the foundation model.** After
  controlling for model choice and benign task completion, target-agent identity
  explains an additional 7.6% of attack-success variation.
- **Safety drift often appears late.** The paper reports that evolved state is
  first consumed around 23% of execution, while the first unsafe output appears
  around 64%; median propagation distance is 37 target actions.
- **Recurring failure modes are compositional.** Agents often fail by keeping
  stale assumptions, propagating earlier safety decisions instead of
  recomputing them, or missing risk created by multiple benign-looking state
  changes.

## Released planner task dataset

The first half/tranche of planner-generated OpenART tasks has been verified and
released as a public Hugging Face dataset.

| Released tasks | Zip shards | Visibility | Status |
| ---: | ---: | --- | --- |
| 6,597 | 34 | public | verified + released |

- Hugging Face dataset:
  [dongdongunique/openart-planner-tasks](https://huggingface.co/datasets/dongdongunique/openart-planner-tasks)
- Validation: checksum, zip integrity, and sample extraction passed.

## Runtime capabilities

OpenART supports reproducible task execution, target-agent evaluation,
attacker-in-the-loop evaluation, Docker-native task isolation, long-horizon
stateful scenarios, and planner-generated environment construction. The same
runtime can be used for lightweight smoke checks, target-only evaluation, and
full red-teaming runs.

## Documentation

See the repository documentation for setup, execution examples, and planner
usage.
