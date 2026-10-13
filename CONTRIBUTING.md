# Contributing to OpenART

Thanks for your interest in improving OpenART! This document covers the
basics for bug reports, feature requests, and pull requests.

## Getting started

1. Fork the repository and clone your fork.
2. Install dependencies:

   ```bash
   cd OpenART
   pip install -r requirements.txt
   ```

3. Verify your setup with the local smoke task (no API keys or model
   backends required):

   ```bash
   cd OpenART
   python -m framework.cli run \
     --task examples/tasks/local-smoke \
     --target-config configs/target-configs/target.local-smoke.yaml \
     --eval-strategy deterministic \
     --skip-attacker \
     --run-id local-smoke \
     --output-dir outputs/local-smoke
   ```

Before any model-backed or Docker-based batch, always run the local smoke
task first.

## Where to start

- Read [`OpenART/skills/openart/SKILL.md`](OpenART/skills/openart/SKILL.md),
  the unified operator guide that routes every task (running evaluations,
  generating tasks, selecting tools, extending the framework, debugging) to
  the right document and command.
- Browse issues labeled `good first issue` or `help wanted`.
- For design and usage background, see [`OpenART/docs/`](OpenART/docs/).

## Making changes

- Prefer the smallest config-driven change; keep taxonomy and command
  behavior centralized in the framework rather than in ad-hoc scripts.
- Follow the style of neighboring code. Do not add comments unless they are
  essential.
- Add or update tests when your change affects framework behavior. The test
  suite lives under [`OpenART/tests/`](OpenART/tests/) (see
  [`OpenART/docs/11_debugging_and_testing.md`](OpenART/docs/11_debugging_and_testing.md)):

  ```bash
  cd OpenART
  python -m pytest
  ```

- Use concise commit messages in the existing style (for example
  `feat: ...`, `docs: ...`, `fix: ...`).

## Safety rules (required)

- Never point attacker flows at external systems, third-party services, or
  non-consenting targets. They exist only to evaluate consenting targets
  inside this repository's Docker sandbox.
- Never commit credentials, API keys, or secrets. Do not copy secrets from
  `.env`, task workspaces, or run artifacts into issues, patches, or commits.
  `OpenART/outputs/` and `.env` are ignored by Git on purpose — keep them
  that way.

## Pull requests

1. Open an issue first for larger changes so we can discuss the approach.
2. Keep PRs focused; one logical change per PR.
3. Fill in the pull request template and describe what changed and why.
4. Make sure the local smoke task and relevant tests pass.

## Reporting bugs

Open a GitHub issue using the bug report template and include:

- What you ran (exact command or config)
- What you expected vs. what happened
- Environment details (OS, Docker, Python version)
- Relevant logs from `OpenART/outputs/` with credentials redacted

## License

By contributing to OpenART, you agree that your contributions will be
licensed under the GNU Affero General Public License v3.0 (see
[LICENSE](LICENSE)).
