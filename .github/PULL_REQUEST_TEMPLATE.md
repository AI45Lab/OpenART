## Summary

Brief description of the change.

## Motivation

Why this change is needed. Link any related issues with `Fixes #NNN` where
applicable.

## Changes

- Key change 1
- Key change 2

## Testing

- [ ] Local smoke task passes:

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

- [ ] Relevant tests under `OpenART/tests/` pass (`python -m pytest`)
- [ ] No credentials, API keys, or secrets are introduced

## Safety check

- [ ] Any attacker flows only target consenting targets inside this
      repository's Docker sandbox
