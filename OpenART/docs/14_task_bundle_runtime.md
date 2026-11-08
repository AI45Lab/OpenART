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
│   ├── docker-compose.yml      GitLab, ownCloud, selected DTAP services
│   ├── task.env                service URLs, credentials, task id
│   ├── ports.env               DTAP port defaults
│   ├── service_assets/         catalog assets used by this task
│   ├── seed/seed_services.py   loads workspace mirrors into the services
│   └── attacker/
│       ├── config.yaml         live-service attacker config
│       └── run.sh              attacker script
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
   optional `bootstrap`.
2. Put any init SQL, migrations, or seed data under
   `services/catalog/assets/<name>/` and list the paths in `assets`.
3. If tools use a new name, add it to `selection.aliases`; if they use a new
   prefix, add it to `selection.tool_prefixes`.
4. Run `python -m framework.task_bundles.generate --dry-run` to confirm the
   task resolves to the new service.

`requires` is transitive: a service can depend on shared catalog services
without repeating their Compose definitions. `bootstrap` selects a generic
post-start step such as `gitlab_token`; omit it for services that need none.

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
2. waits for GitLab;
3. creates a GitLab personal access token with `gitlab-rails runner`;
4. writes the token to `docker/task.env`;
5. runs the seed job.

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
`GITLAB_*`, `OWNCLOUD_*`, and `DTAP_*` variables from the attacker and does not
attach it to the task network. When it is present, the attacker joins the
network and receives the same service credentials as the target.

The attacker has two channels:

- workspace files, applied through the normal OpenART file diff;
- live service writes, applied directly through GitLab/ownCloud/DTAP APIs.

Set `OPENART_ATTACK_SERVICE_WRITE=1` to exercise the live-service channel in
the generated `run.sh`. The orchestrator forwards that variable and
`OPENART_ATTACKER_MARKER` to the attacker runtime environment. Without
`service_state`, the attacker does not receive `GITLAB_*`, `OWNCLOUD_*`, or
`DTAP_*` credentials, including credentials injected through attacker
`env`/`env_from` entries.

## Pre-evaluation service export

The planner evaluator reads workspace files only. The generated bundle adds:

```text
OPENART_PRE_EVAL_HOOK=/opt/openart-venv/bin/python3 /task/finalize/export_services.py
```

`Orchestrator._run_pre_eval_hook()` runs the hook inside the task container
before every workspace snapshot/evaluation. The hook:

- reads the live GitLab project tree and file contents;
- reads the ownCloud WebDAV tree and file contents;
- writes them into the evaluator roots parsed from
  `planner_plan.json` and `utils/evaluator.py`;
- writes `workspace/.openart/service_export.json` for inspection.

Evaluator roots are normalized to paths relative to the mounted workspace:
`workspace/gitlab_snapshots`, `workspace / 'owncloud_uploads'`, and
`workspace / "owncloud_mirror" / "uploads"` all become relative roots such as
`gitlab_snapshots` or `owncloud_mirror/uploads`. When several roots match a
service, the export uses the most specific directory (the longest path) and
ignores file-like roots such as `output/thread_summary.md`. This keeps
chained roots such as `owncloud_mirror/uploads` intact.

The seed job also waits for every selected DTAP health endpoint before it
returns, so the target does not start against a service that is still booting.

If the hook fails, the run fails instead of silently grading an incomplete
workspace.

## Network modes

### Bridge (default)

- one private network per task: `openart-<task_id>-net`;
- services resolve by Compose DNS name;
- GitLab listens on `gitlab:8929`;
- ownCloud listens on `owncloud:8080`;
- GitLab/ownCloud host ports are random loopback ports for debugging;
- concurrent tasks do not share service ports.

### Host (fallback)

- all services use `network_mode: host`;
- the task/runner/attacker containers join the host network;
- service URLs use `127.0.0.1`;
- only one task can run per host because the DTAP images use fixed ports.

Use host mode only when a DTAP image cannot run on a bridge network.

## Validation status

The bridge path was verified end to end on `openart-mid-000001`:

1. All 15 services for the task, including GitLab, ownCloud, PostgreSQL
   sidecars, the Google IdP, and the DTAP APIs/UIs, became healthy on
   `openart-mid-000001-net`.
2. `up.sh` created the GitLab root user and personal access token, then
   seeded GitLab and ownCloud from the task workspace.
3. The live-service attacker joined the network and wrote a marker to both
   GitLab and ownCloud when `OPENART_ATTACK_SERVICE_WRITE=1`.
4. `export_services.py` ran before evaluation and copied the live state into
   `gitlab_snapshots/` and `owncloud_uploads/`.
5. The deterministic evaluator detected the exported marker in both roots.

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
Compose rendering in bridge/host modes, bundle generation, adding a service
through a temporary catalog without touching framework code, and the opt-in
`service_state` permission.