# OpenAgentSafety Utils

Generic user-provided tool bundle for OpenART runs.

Use it with:

```bash
python -m framework.cli run \
  --task ../openagentsafety/tasks/<task-name> \
  --tools-file openagentsafety_utils/user-tools.yaml
```

Required environment variables:

- `GITLAB_BASEURL`
- `GITLAB_ACCESS_TOKEN`
- `OWNCLOUD_URL`
- `OWNCLOUD_USERNAME`
- `OWNCLOUD_PASSWORD`

These tools are generic local wrappers. OpenART copies this folder into the runner and adds the generated wrapper commands to `PATH`.
