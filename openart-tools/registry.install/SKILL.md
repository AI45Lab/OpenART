---
name: registry.install
description: Install GitHub-hosted registry skill folders into the OpenART tool store as guide-only tools.
---

Use this skill when a host-side operator needs to install one or more registry entries from GitHub folder or file URLs into the OpenART tool store.

This helper accepts registry ids, resolves each row's GitHub URL, downloads the selected folder or file through the GitHub REST API, validates the result offline, and installs it as `openart-tools/<virtual_tool_name>/`.

It does not execute downloaded scripts, does not create a runtime wrapper, and does not synthesize `tool.yaml`. If an upstream top-level `tool.yaml` exists, it is preserved as `references/original_tool.yaml`.

Example:

```bash
python3 openart-tools/registry.install/scripts/registry_install.py \
  --index openart-tools/.registry/openart_tool_registry.sqlite \
  --ids ids.txt \
  --tool-store openart-tools
```
