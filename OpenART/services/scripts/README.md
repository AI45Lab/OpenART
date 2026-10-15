# Service Scripts

Utility scripts for managing OpenART services.

## Quick Reference

| Script | Purpose |
|--------|---------|
| `start_all_services.sh` | Start all services (all profiles) |
| `stop_all_services.sh` | Stop all services and remove volumes |
| `get_service_status.sh` | Get status of all services (docker ps + health checks) |
| `health_check_all.sh` | Health-check all running services |

## Usage

```bash
# Start everything
bash OpenART/services/scripts/start_all_services.sh

# Start only dtap services
bash OpenART/services/scripts/start_all_services.sh --profile dtap

# Stop everything
bash OpenART/services/scripts/stop_all_services.sh

# Check status
bash OpenART/services/scripts/get_service_status.sh
```

## Environment

All scripts respect:

- `SERVICE_DIR` (default: `OpenART/images/services`) — source compose dir
- `PORTS_ENV` (default: `$SERVICE_DIR/ports.env`) — central port config

Scripts are idempotent and safe to re-run.
