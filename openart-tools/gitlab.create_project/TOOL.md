# gitlab.create_project

Create a GitLab project using `GITLAB_BASEURL` and `GITLAB_ACCESS_TOKEN`.

## Usage

```bash
gitlab.create_project internal-api-client public
```

The first argument is the project name. The optional second argument is the GitLab visibility, defaulting to `public`.

## Environment

- `GITLAB_BASEURL`
- `GITLAB_ACCESS_TOKEN`

Aliases accepted by OpenART service resolution include `GITLAB_URL`, `GITLAB_WEB_URL`, `GITLAB_TOKEN`, and `GITLAB_PRIVATE_TOKEN`.

## Side Effects

Creates a remote GitLab project.
