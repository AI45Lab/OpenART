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

If the model endpoint needs a proxy, prefer one reachable from the container
network and put it in the attacker `env`; no host networking is needed. Only
when the proxy binds to the host loopback should you run the attacker with
`OPENART_ATTACKER_DOCKER_NETWORK=host`. Do not route large prompts through a
bridge-network relay.

## Native evaluator task

`cua-smoke-file` is a plumbing smoke test with a synthetic evaluator. To score
an actual Lite.OSWorld task, use
`tasks/osworld-e0df059f-rename-todo-dir`, which runs OSWorld task
`e0df059f-28a6-4169-924f-b9623e7184cc` and grades it with the benchmark's own
evaluator:

```text
tasks/osworld-e0df059f-rename-todo-dir/
├── Dockerfile              FROM the pinned Lite.OSWorld image
├── task.md                 upstream OSWorld instruction (verbatim)
├── env/setup.sh            desktop stack + upstream task setup
├── agent/cua_agent.py      scripted oracle (--mode oracle) / control (--mode noop)
├── utils/task_spec.json    upstream evaluator config (pinned commit)
└── utils/evaluator.py      OSWorld getter + metric (`vm_command_line`, `rule`, `exact_match`)
```

The getter and metric bodies are copied from OSWorld commit
`5123bfdbbc34b947bcffcff564abc62d0ab7072d` and run inside the task container,
reaching the desktop through the image's local OSWorld server
(`http://127.0.0.1:5000`). The evaluator config is the upstream one, unmodified.

Run the oracle and the negative controls with `--skip-attacker`, then compare
`result.json`:

```bash
cd OpenART
python3 -m framework.cli run \
  --task benchmarks/capability-bundles/lite-osworld/tasks/osworld-e0df059f-rename-todo-dir \
  --target-config benchmarks/configs/target-configs/target.cua-osworld.yaml \
  --runner-mode in_container \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id cua-native-oracle \
  --output-dir /tmp/openart-cua-native
```

`target.cua-osworld.yaml` launches `agent/cua_agent.py --mode oracle`. Switch
its `launch_cmd` to `--mode noop` (leave the desktop untouched) or
`--mode wrong` (rename to the wrong name) for negative controls; the native
evaluator must return `score=0.0` for both and `1.0` for the oracle.