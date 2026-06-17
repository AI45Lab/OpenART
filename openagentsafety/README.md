---
license: cc-by-4.0
language:
  - en
task_categories:
  - other
pretty_name: OpenAgentSafety
tags:
  - agent-evaluation
  - csv-index
  - ai-safety
---

## Overview

**OpenAgentSafety (OAS)** is an open-source benchmark built on top of [TheAgentCompany](https://github.com/TheAgentCompany/TheAgentCompany) to systematically evaluate the safety of LLM-based agents operating in realistic, high-risk environments. Agents interact with real tools like file systems, terminals, browsers, and messaging platforms, and must navigate complex multi-turn tasks involving ambiguous, conflicting, or adversarial user instructions. OAS tasks are grounded in practical deployment scenarios and designed to reveal safety failures that occur only during dynamic multi-step interactions.

## Key Features
- **High-risk tasks** with real-world tooling (code, files, web, chat)
- **Adversarial + ambiguous prompts** from simulated users/NPCs
- **Multi-turn reasoning** in dynamic environments
- **Rich safety evaluation** via deterministic + LLM-based scoring
- **Built on robust agent evaluation and complex social frameworks TheAgentCompany + Sotopia foundations**

## Dataset

This dataset contains tasks designed for evaluating agent behavior under adversarial or ambiguous conditions.

Explanations:
  - tasks is the folder for definitions of all 356 tasks, within which
  - evaluator.py defines the rule-based grading functions
  - checkpoints.md is the documentation for the expected malicious behavior (for human reference or LLM-as-judge only)
  - dependencies.yml defines the list of service dependencies
  - task.md is the task specification, contains background and requirements of each task, and is the **only** file that should be prompted to agents
  - `workspace/`: input files required by the task (e.g., `.csv`, `.txt`)

## 📌 Citation

Citation coming soon. For now, please refer to the GitHub repository:

> https://github.com/sani903/OpenAgentSafety

## 📝 License

All content in this dataset repository is licensed under the [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).

## 🙋 Contributing

We welcome contributions and issue reports!

