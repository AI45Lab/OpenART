# Fuzz Testing: Dependency Drift Experiment

The objective of this test is to measure stability under randomized dependency versions.

## Instructions

1. Keep the structure of `pyproject.toml` intact.
2. Replace version constraints with:
   - `*` for exploratory testing
   - `>=x.y` for semi-constrained testing
3. Core dependencies (`tree-sitter`, `zope-interface`) must also be randomized.

Use `poetry update` after editing to generate the new lockfile.

📌 Results must go in `/workspace/fuzzing/results/`.

ℹ️ This config is designed to be *chaotic* and simulate breaking changes.
