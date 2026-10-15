# DTAP Services

DTAP (DecodingTrust-Agent Platform) services provide realistic web-based
service surfaces for OpenART scenario evaluation. Each environment is a
multi-container Docker Compose stack with API + UI (+ DB) tiers.

## Environments

| Env | Compose file (in DTAP repo) | Base port | Containers |
|-----|----------------------------|-----------|------------|
| finance | `dt_arena/envs/finance/docker-compose.yml` | 23000 | finance-web |
| legal | `dt_arena/envs/legal/docker-compose.yml` | 23100 | legal-web |
| gmail | `dt_arena/envs/gmail/docker-compose-hub.yml` | 24000 | gmail-mailpit, gmail-service, gmail-ui |
| slack | `dt_arena/envs/slack/docker-compose-hub.yml` | 24500 | slack-api, slack-ui |
| calendar | `dt_arena/envs/calendar/docker-compose-hub.yml` | 24600 | calendar-api, calendar-ui |
| zoom | `dt_arena/envs/zoom/docker-compose-hub.yml` | 24700 | zoom-api, zoom-ui |
| paypal | `dt_arena/envs/paypal/docker-compose-hub.yml` | 25000 | paypal-pg, paypal-api, paypal-ui |
| atlassian | `dt_arena/envs/atlassian/docker-compose-hub.yml` | 25100 | atlassian-pg, atlassian-api, atlassian-ui |
| github | `dt_arena/envs/github/docker/docker-compose-hub.yml` | 25200 | github-db, github-api, github-ui |
| google-form | `dt_arena/envs/google-form/docker-compose-hub.yml` | 25300 | google-form-api, google-form-ui |
| googledocs | `dt_arena/envs/googledocs/docker-compose-hub.yml` | 25400 | googledocs-db, googledocs-api, googledocs-ui |
| telegram | `dt_arena/envs/telegram/docker-compose-hub.yml` | 25500 | telegram-pg, telegram-api |
| whatsapp | `dt_arena/envs/whatsapp/docker-compose-hub.yml` | 25600 | whatsapp-pg, whatsapp-api, whatsapp-ui |
| snowflake | `dt_arena/envs/snowflake/docker-compose-hub.yml` | 25700 | snowflake-pg, snowflake-admin |
| databricks | `dt_arena/envs/databricks/docker-compose-hub.yml` | 25800 | databricks-pg, databricks-admin |
| bigquery | `dt_arena/envs/bigquery/docker-compose.yml` | 25900 | bigquery |

## How to Run (docker compose, all 16 DTAP environments)

The compose file pulls public images from Docker Hub
(`decodingtrustagent/<role>`), starts all 16 DTAP environments with
`network_mode: host`, and exposes health/ports endpoints.

```bash
cd OpenART/images/services
docker compose --env-file ports.env -f docker-compose.yml --profile dtap up -d
```

To start/stop an individual environment on the service host:

```bash
bash Servers/dtap_start_env.sh <env-name> <base-port> [project-name] [dtap-repo-root]
# e.g.
bash Servers/dtap_start_env.sh gmail 24000 gmail-0 \
  /mnt/shared-storage-user/chenyunhao/DecodingTrust-Agent.internal

bash Servers/dtap_stop_env.sh <env-name> <project-name> [dtap-repo-root]
```

Environment artifacts are written to `/tmp/<project>.env` and
`/tmp/<project>.registry.json`.

## How to Run (local docker, all DTAP services)

```bash
cd OpenART/images/services
docker compose --env-file ports.env -f docker-compose.yml --profile dtap up -d
```

## How to Run (local docker, selected DTAP services)

```bash
cd OpenART/images/services
docker compose --env-file ports.env -f docker-compose.yml up -d \
  dtap-gmail-mailpit dtap-gmail-service dtap-gmail-ui dtap-slack-api
```

## Endpoints and Ports

Ports are defined in `OpenART/images/services/ports.env` (all DTAP services
use `network_mode: host`):

```
FINANCE_WEB_PORT=23000        LEGAL_WEB_PORT=23100
GMAIL_SMTP_PORT=24000         GMAIL_AUTH_PORT=24001     GMAIL_PROXY_PORT=24002
GMAIL_UI_PORT=24003           GMAIL_FRONTEND_PORT=24004
SLACK_API_PORT=24500          SLACK_UI_PORT=24501
CALENDAR_API_PORT=24600       CALENDAR_UI_PORT=24601
ZOOM_API_PORT=24700           ZOOM_UI_PORT=24701
PAYPAL_PG_PORT=25000          PAYPAL_API_PORT=25001     PAYPAL_UI_PORT=25002
ATLASSIAN_DB_PORT=25100       ATLASSIAN_API_PORT=25101  ATLASSIAN_UI_PORT=25102
GITHUB_PG_PORT=25200          GITHUB_API_PORT=25201     GITHUB_UI_PORT=25202
GOOGLE_FORM_API_PORT=25300    GOOGLE_FORM_UI_PORT=25301
GOOGLEDOCS_PG_PORT=25400      GOOGLEDOCS_API_PORT=25401 GOOGLEDOCS_FRONTEND_PORT=25402
TELEGRAM_PG_PORT=25500        TELEGRAM_API_PORT=25501
WHATSAPP_PG_PORT=25600        WHATSAPP_API_PORT=25601   WHATSAPP_FRONTEND_PORT=25602
SNOWFLAKE_PG_PORT=25700       SNOWFLAKE_ADMIN_PORT=25701
DATABRICKS_PG_PORT=25800      DATABRICKS_ADMIN_PORT=25801
BIGQUERY_API_PORT=25900
```

OpenART `dtap.*` wrapper endpoint exports are in
`OpenART/images/services/openart-endpoints.env`. To use the DTAP wrappers:

```bash
set -a
source OpenART/images/services/openart-endpoints.env
set +a
```

## Images

DTAP images are public on Docker Hub under the `decodingtrustagent` org:

```
decodingtrustagent/<role>:<tag>
```

For example: `decodingtrustagent/gmail:service-latest`,
`decodingtrustagent/github:db-latest`, `decodingtrustagent/snowflake:admin`.

## Health Checks

Each environment exposes a health endpoint:

```bash
curl --noproxy '*' -fsS http://127.0.0.1:24001/health   # gmail
curl --noproxy '*' -fsS http://127.0.0.1:24500/health   # slack
curl --noproxy '*' -fsS http://127.0.0.1:23000/api/health  # finance
```

See the master [services README](../README.md) for the full health-check
table.
