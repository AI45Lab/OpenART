# Lite.OSWorld Task-Container Smoke

This benchmark sample runs one real Lite.OSWorld desktop image as an OpenART
task container. The image is `ghcr.io/cua-lite/lite.osworld:latest`.

```text
tasks/cua-smoke-file/
├── Dockerfile              FROM the Lite.OSWorld image
├── task.md                 benign GUI instruction
├── env/setup.sh            starts supervisord, waits for GNOME + OSWorld server
├── agent/cua_agent.py      scripted desktop agent (xdotool via /execute)
└── utils/evaluator.py      checks the file created on the desktop
```

Run it in-container (the agent shares the desktop's OS and localhost) with the
framework Graph-RL attacker:

```bash
cd OpenART
python3 -m framework.cli run \
  --task benchmarks/capability-bundles/lite-osworld/tasks/cua-smoke-file \
  --target-config benchmarks/configs/target-configs/target.cua-smoke.yaml \
  --attacker-config benchmarks/configs/attacker-configs/graph-rl-control/config.yaml \
  --runner-mode in_container \
  --eval-strategy deterministic \
  --run-id cua-smoke \
  --output-dir /tmp/openart-cua-smoke
```

The task Dockerfile is built automatically. The agent is a scripted smoke
agent, not a vision-language CUA policy; it validates the Docker, setup,
desktop, attacker, evaluator, and runner-placement plumbing end to end.