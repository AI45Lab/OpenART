# Evaluator Harness Utilities

This directory contains compatibility helpers for deterministic evaluators that
expect shared modules such as `config`, `common`, or `scoring`.

Most bundled generated OpenART tasks do not need this harness. When a task does
need shared evaluator imports, pass the directory explicitly:

```bash
python -m framework.cli run \
  --task examples/tasks/<task-name> \
  --evaluator-harness openagentsafety_utils/oas_harness \
  --tool-store ../openart-tools
```

Managed tools live in the sibling `openart-tools/` store. Tasks with
`tool_use_graph.json` receive only referenced tools.
