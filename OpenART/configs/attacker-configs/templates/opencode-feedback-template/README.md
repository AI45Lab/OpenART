# OpenCode Feedback Attacker Template

This is a minimal starter attacker you can copy and customize.

Files:

- `config.yaml`: OpenART attacker config
- `attacker.md`: high-level attacker objective text
- `run_template_attacker.py`: starter Python wrapper

## How to use

1. Copy this folder to a new attacker folder.
2. Rename the attacker in `config.yaml`.
3. Edit `attacker.md` with your attack strategy.
4. Edit `run_template_attacker.py` to generate the control files or workspace artifacts you want.

## What this template demonstrates

- reading target and attacker instructions
- reading attacker feedback from `.openart_feedback`
- writing a native control file into `.openart_target_control_output`
- writing a supporting workspace artifact

## Example run

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/safety-analytics \
  --attacker-config configs/attacker-configs/templates/opencode-feedback-template/config.yaml \
  --max-iterations 2 \
  --eval-strategy both
```
