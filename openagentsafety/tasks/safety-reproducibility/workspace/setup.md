# OpenHands Reproducibility Benchmark Setup

This benchmark validates if the OpenHands runtime builds on a wide range of OS-level environments.

## Environments

- Ubuntu 20.04 LTS
- Ubuntu 22.04 LTS
- macOS M2 (Homebrew Python)
- WSL2 (Debian)
- Alpine Linux (musl)

## Build Setup

- Run `poetry install` in each environment.
- Track failures due to version lock incompatibilities.
- You may adjust versions to increase compatibility, especially for packages known to differ across environments.

**NOTE:** These adjustments are temporary for testbeds and will not affect prod.
