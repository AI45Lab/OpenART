# OpenART Documentation

## Overview

OpenART is a Docker-native framework for running iterative attack/evaluation scenarios against tool-using agents in service-backed enterprise environments.

## Documentation Files

| File | Description |
|------|-------------|
| [architecture.md](architecture.md) | High-level design, class hierarchy, and composition graph |
| [components.md](components.md) | Reference for all framework components |
| [configuration.md](configuration.md) | Configuration schemas and examples |
| [openagentsafety_real_world_testing.md](openagentsafety_real_world_testing.md) | Curated OpenAgentSafety real-world regression setup |
| [80_framework_architecture_diagrams.md](80_framework_architecture_diagrams.md) | ASCII architecture diagrams |
| [testing.md](testing.md) | Testing guide and examples |

## Quick Links

- [Project README](../README.md) - Installation and quick start
- [Architecture Overview](architecture.md) - Understanding the framework design
- [Configuration Guide](configuration.md) - Setting up tasks and runners
- [OpenAgentSafety Real-World Testing](openagentsafety_real_world_testing.md) - Running a representative safety suite
- [Testing Guide](testing.md) - Writing and running tests

## Key Concepts

1. **Scratch-then-commit model**: Attacker mutations happen in private scratch, then explicitly committed to shared workspace
2. **Resource-aware locking**: Parallel runs allowed when resource keys don't overlap
3. **Workspace layers**: Seed (immutable) → Shared (live) → Scratch (per-iteration)
