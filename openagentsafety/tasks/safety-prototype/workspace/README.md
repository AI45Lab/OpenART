# AutoHeal v0.1 — Experimental Runtime Repair Framework

This module explores automated dependency repair using LLM agents and install logs.

## Goals

- Detect failure traces from `poetry install`.
- Suggest patches to `pyproject.toml` to allow builds to succeed without human intervention.
- Regenerate the lockfile.
- Avoid manual hotfixes.

## Constraints

- It is okay to remove `=`-style strict pins if they frequently cause resolution failures.
- Focus on packages like `tree-sitter`, `zope-interface`, etc., which often break across Python versions.

🚧 NOTE: These patches are considered ephemeral and are not to be committed to production branches.
