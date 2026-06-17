# gitlab.upload_file

Create or update a text file in a GitLab repository branch using the configured GitLab token.

## Usage

```bash
gitlab.upload_file root/internal-api-client /workspace/client.py client.py main "Add client.py"
```

Arguments are repository path, local file, optional remote file path, optional branch, and optional commit message.

## Environment

- `GITLAB_BASEURL`
- `GITLAB_ACCESS_TOKEN`

Aliases accepted by OpenART service resolution include `GITLAB_URL`, `GITLAB_WEB_URL`, `GITLAB_TOKEN`, and `GITLAB_PRIVATE_TOKEN`.

## Side Effects

Writes or updates a remote repository file and creates a commit.
