# Lite.OSWorld Task-Container Smoke

This benchmark sample runs one real Lite.OSWorld desktop image as an OpenART
task container. The image is pinned by digest:
`ghcr.io/cua-lite/lite.osworld@sha256:2d51f12e1bff4a8621c3a810cd5399c2c678aafae0db310f757c8c240cf954b1`.

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

Graph-RL plans attacks with `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and
`OPENAI_MODEL`. If no model quota is available, pass the attacker a
precomputed plan with `--graph-file`; the rest of the container, validation,
sampling, and materialization path is unchanged.

If the model endpoint is only reachable through a proxy bound to the host
loopback, run the attacker on the host network with
`OPENART_ATTACKER_DOCKER_NETWORK=host` and give the attacker `env` the proxy
settings. Do not route large prompts through a bridge-network relay.