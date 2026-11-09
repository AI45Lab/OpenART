# Per-Task Docker Compose Bundles

This document describes `framework.task_bundles`, the generator that turns one
OpenART planner task into a self-contained Docker Compose bundle.

The bundle starts only the services selected by the task's
`tool_use_graph.json`. It is not a single image per task; it is a small
generated Compose project plus the original task files.

## What the generator produces

```text
openart-mid-000001/
├── task/                       original task + generated finalize/ and attacker/
├── docker/
│   ├── docker-compose.yml      selected catalog services
│   ├── task.env                service URLs, credentials, task id
│   ├── ports.env               service port defaults
│   ├── service_assets/         catalog assets used by this task
│   ├── hooks/                  catalog bootstrap hooks
│   ├── seed/
│   │   ├── seed_services.py    waits for health, runs catalog seed hooks
│   │   └── hooks/              catalog seed hooks
│   └── attacker/
│       ├── config.yaml         live-service attacker config
│       ├── run.sh              generic attacker runner
│       └── hooks/              catalog attacker hooks
├── runs/                       OpenART output
├── up.sh
├── run.sh
└── down.sh
```

## Service selection

`extract_required_services()` reads:

- `tool_use_graph.json` — the tools the task's safe and unsafe workflows use
- `tool_pool.json` — the `service` field for each tool

It maps tool names to catalog services and then to Compose services:

```text
dtap.slack          -> slack       -> dtap-slack-api, dtap-slack-ui
gitlab.get_file     -> gitlab      -> gitlab
owncloud.upload_file-> owncloud    -> owncloud, owncloud-db, owncloud-redis
```

Services not present in the tool graph are never started. Unknown service
names are reported in the generator output so the catalog can be extended.

Real planner tasks sometimes carry a generic pool value such as `dtap` for a
concrete `dtap.atlassian` tool, or a local category such as `workspace`,
`document`, `tool`, or `skill` for tools that do not need a service. The
extractor treats the tool-name prefix as authoritative, normalizes aliases
such as `google_form` to `google-form`, and skips local categories. On the
current `mid` corpus this resolves all 1,046 tasks to known services with no
unknown entries.

## Service catalog

Concrete service names, images, Compose definitions, ports, endpoint
environment, dependencies, and seed assets live outside the framework in
`services/catalog/services.yaml` (assets under `services/catalog/assets/`).
The framework only knows the catalog schema and a small set of placeholders.
Adding a service is therefore a catalog change, not a framework change:

1. Add an entry under `services.services.<name>` with `compose`, `roles`,
   `ports`, optional `host_ports`, `task_env`, `requires`, `assets`, and
   optional `hooks`.
2. Put any init SQL, migrations, seed data, or hook scripts under
   `services/catalog/assets/<name>/` and list non-hook data paths in `assets`.
3. If tools use a new name, add it to `selection.aliases`; if they use a new
   prefix, add it to `selection.tool_prefixes`.
4. Run `python -m framework.task_bundles.generate --dry-run` to confirm the
   task resolves to the new service.

`requires` is transitive: a service can depend on shared catalog services
without repeating their Compose definitions.

## Service hooks

Services can provide behavior without any framework change. A hook is a
directory (or a single script) under the service's catalog assets with a
`run.py` or `run.sh` entrypoint:

```yaml
services:
  acme:
    compose: { ... }
    hooks:
      bootstrap: acme/hooks/bootstrap
      seed: acme/hooks/seed
      export: acme/hooks/export
      attacker: acme/hooks/attacker
```

| Hook | Runs in | Purpose |
| --- | --- | --- |
| `bootstrap` | host, after `up -d` | Create tokens, wait for readiness, prepare host-side state |
| `seed` | seed container | Load workspace mirrors into the live service |
| `export` | task container, pre-eval | Copy live service state into evaluator roots |
| `attacker` | attacker container | Optional live-service write when `OPENART_ATTACK_SERVICE_WRITE=1` |

The generator copies hooks to:

```text
docker/hooks/<service>/                    # bootstrap
docker/seed/hooks/<service>/               # seed
task/finalize/hooks/<service>/             # export
docker/attacker/hooks/<service>/           # attacker
```

Hook environment:

```text
OPENART_SERVICE_NAME          logical catalog service name
OPENART_HOOK_DIR              directory containing the hook
OPENART_BUNDLE_DIR            bundle root (bootstrap)
OPENART_TASK_ENV_FILE         docker/task.env (bootstrap)
OPENART_COMPOSE_FILE          docker/docker-compose.yml (bootstrap)
OPENART_SEED_WORKSPACE        workspace mirror root (seed)
OPENART_WORKSPACE             evaluator workspace (export)
OPENART_PUBLIC_ROOTS_JSON     evaluator roots (export)
OPENART_TASK_ROOT             /task (export)
OPENART_RUN_ID                run id (attacker)
OPENART_ATTACKER_MARKER       marker value (attacker)
```

A hook prints one JSON object on success. The generic runners aggregate those
objects into the seed output or `.openart/service_export.json`.

Minimal new-service example:

```yaml
services:
  acme:
    compose:
      acme-api:
        image: example/acme:latest
        environment:
          ACME_PORT: "{{ api_port }}"
    roles:
      api: acme-api
    ports:
      api: "26000"
    task_env:
      ACME_URL: "{{ url:acme-api:26000 }}"
    hooks:
      seed: acme/hooks/seed
      export: acme/hooks/export
```

```text
services/catalog/assets/acme/hooks/seed/run.py
services/catalog/assets/acme/hooks/export/run.py
```

Then generate and start normally:

```bash
python -m framework.task_bundles.generate \
  --task /path/to/task \
  --out /path/to/bundle \
  --target-config /path/to/target.yaml \
  --force
cd /path/to/bundle
./up.sh
```

If task tools use a new name or prefix, add it to `selection.aliases` or
`selection.tool_prefixes`. No framework file changes are required.

Catalog placeholders:

```text
{{ bind_host }}         0.0.0.0 in bridge, 127.0.0.1 in host mode
{{ pg_host }}           role "pg" host: Compose DNS name or 127.0.0.1
{{ pg_port }}           role "pg" port: container port or host-mapped port
{{ pg_addr }}           "pg_host:pg_port" for the current service
{{ role_host:<role> }}  host of a named role (db, redis, api, ...)
{{ host:<compose> }}    Compose service DNS name, or 127.0.0.1 in host mode
{{ url:<compose>:<p> }} http URL to a Compose service and port
{{ api_port }}          service role "api" port
{{ ui_port }}           service role "ui" port
{{ asset:<path> }}      ./service_assets/<path> in the generated bundle
```

`--service-catalog` (or `OPENART_SERVICE_CATALOG`) overrides the catalog path.
The path may be a single YAML file or a directory of YAML fragments. A file
catalog can also be extended by dropping fragments into
`services/catalog/services.d/*.yaml`; the loader merges `services`,
`selection`, and `defaults`. This makes a new service a one-file catalog
addition plus its assets.

## Generate a bundle

```bash
python -m framework.task_bundles.generate \
  --task /path/to/openart-mid-000001 \
  --out /path/to/bundles/openart-mid-000001 \
  --target-config /path/to/target.yaml \
  --network-mode bridge \
  --service-catalog services/catalog/services.yaml \
  --force
```

`--target-config` is required. The generated `run.sh` fails if the target
config is missing; it does not fall back to an implicit OpenCode target.

Use `--dry-run` to inspect the selected services and evaluator roots without
writing anything:

```bash
python -m framework.task_bundles.generate \
  --task /path/to/task \
  --out /tmp/unused \
  --target-config /tmp/target.yaml \
  --dry-run
```

## Run a bundle

```bash
cd /path/to/bundles/openart-mid-000001
./up.sh
OPENART_TARGET_CONFIG=/path/to/target.yaml ./run.sh
./down.sh
```

`up.sh`:

1. starts the selected services;
2. runs every selected service's `bootstrap` hook;
3. runs the seed job, which waits on catalog health URLs and runs every
   selected service's `seed` hook.

`down.sh` removes the Compose project and all service volumes.

## Attacker live-service access

The generated attacker config explicitly opts in:

```yaml
attacker:
  name: live-service-attacker
  phase: before_target
  network: openart-<task_id>-net
  vector_permissions: [workspace_files, service_state]
```

`service_state` is opt-in. When it is absent, `OrchestratorFactory` strips
the credential prefixes declared by the catalog
(`selection.credential_prefixes`, or prefixes derived from catalog env names)
and does not attach the attacker to the task network. When it is present, the
attacker joins the network and receives the same service credentials as the
target.

The attacker has two channels:

- workspace files, applied through the normal OpenART file diff;
- live service writes, applied by the catalog `attacker` hooks.

Set `OPENART_ATTACK_SERVICE_WRITE=1` to exercise the live-service channel in
the generated `run.sh`. The orchestrator forwards that variable and
`OPENART_ATTACKER_MARKER` to the attacker runtime environment. Without
`service_state`, the attacker does not receive catalog credentials, including
credentials injected through attacker `env`/`env_from` entries.

## Pre-evaluation service export

The planner evaluator reads workspace files only. The generated bundle adds:

```text
OPENART_PRE_EVAL_HOOK=/opt/openart-venv/bin/python3 /task/finalize/export_services.py
```

`Orchestrator._run_pre_eval_hook()` runs the hook inside the task container
before every workspace snapshot/evaluation. The generic runner executes each
selected service's `export` hook. Each hook:

- reads its live service state;
- writes into the evaluator roots parsed from `planner_plan.json` and
  `utils/evaluator.py`;
- returns a JSON summary.

The runner aggregates every hook result into
`workspace/.openart/service_export.json` for inspection.

Evaluator roots are normalized to paths relative to the mounted workspace.
When several roots match a service, a hook can use the shared
`hook_common.root_for()` helper to pick the most specific directory (the
longest path) and ignore file-like roots such as `output/thread_summary.md`.

The seed job waits for every catalog health URL before running seed hooks, so
the target does not start against a service that is still booting.

If the hook fails, the run fails instead of silently grading an incomplete
workspace.

## Network modes

### Bridge (default)

- one private network per task: `openart-<task_id>-net`;
- services resolve by Compose DNS name;
- catalog ports define the endpoints used by `task.env`;
- published host ports are random loopback ports for debugging;
- concurrent tasks do not share service ports.

### Host (fallback)

- all services use `network_mode: host`;
- the task/runner/attacker containers join the host network;
- service URLs use `127.0.0.1`;
- only one task can run per host because the DTAP images use fixed ports.

Use host mode only when a DTAP image cannot run on a bridge network.

## Validation status

The bridge path was verified end to end on `openart-mid-000001`:

1. All 15 services for the task, including database sidecars, the identity
   service, and the application APIs/UIs, became healthy on the per-task
   network.
2. `up.sh` ran the catalog bootstrap hook, then the catalog seed hooks.
3. The live-service attacker joined the network and ran the catalog attacker
   hooks when `OPENART_ATTACK_SERVICE_WRITE=1`.
4. `export_services.py` ran the catalog export hooks before evaluation.
5. The deterministic evaluator detected the exported service-side marker.

All 1,046 `mid` tasks resolve to catalog services with zero unknown names, and
the generator produced one bundle per task without failures.

GitLab's first boot performs database migrations and can take a long time on a
busy host. The Compose health check allows 40 minutes. Reusing a per-task
volume avoids repeated migrations; deleting volumes with `down.sh` restores a
clean first boot.

The DTAP images were originally documented for `network_mode: host`; bridge
mode now works when the Docker daemon has working DNS and iptables. The
generator keeps host mode as the fallback.

## Tests

```bash
pytest tests/unit/test_task_bundles.py -q
```

The tests cover catalog loading, service extraction, evaluator-root parsing,
Compose rendering in bridge/host modes, bundle generation, hook copying,
adding a service through a temporary catalog without touching framework code,
and the opt-in `service_state` permission. One test asserts that framework
code and templates contain no concrete service names.