---
name: registry.install
description: Install GitHub-hosted registry skill folders into the OpenART tool store as guide-only or wrapper-backed script tools.
---

Use this skill when a host-side operator needs to install one or more registry entries from GitHub folder or file URLs into the OpenART tool store.

This helper accepts registry ids, resolves each row's GitHub URL, downloads the selected folder or file through the GitHub REST API, validates the result offline, and installs it as `openart-tools/<virtual_tool_name>/`.

If the upstream skill contains `scripts/`, it writes a generated `scripts/openart_skill_runner.py` wrapper plus a local OpenART `tool.yaml`; the upstream `tool.yaml` is preserved as `references/original_tool.yaml` and is not trusted. If the upstream skill has no `scripts/`, only normalized `SKILL.md` and preserved references are installed.

Example:

```bash
python3 openart-tools/registry.install/scripts/registry_install.py \
  --index openart-tools/.registry/openart_tool_registry.sqlite \
  --ids ids.txt \
  --tool-store openart-tools
```
