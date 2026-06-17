# gitlab.get_file

Print a GitLab repository file at a specific ref.

## Usage

```bash
gitlab.get_file root/internal-api-client client.py main
```

Arguments are repository path, file path, and optional ref. The ref defaults to `main`.

## Environment

- `GITLAB_BASEURL`
- `GITLAB_ACCESS_TOKEN`

Aliases accepted by OpenART service resolution include `GITLAB_URL`, `GITLAB_WEB_URL`, `GITLAB_TOKEN`, and `GITLAB_PRIVATE_TOKEN`.

## Side Effects

Reads remote GitLab content.
