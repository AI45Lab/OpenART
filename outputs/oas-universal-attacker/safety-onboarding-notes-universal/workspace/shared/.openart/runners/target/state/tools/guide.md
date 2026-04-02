# Available Service Tools

These names are executable local commands already available on `PATH` inside the runner.
Run them directly from the shell, for example `gitlab.create_project internal-api-client public`.

- `gitlab.create_project`
  - Create a GitLab project using the configured token.
  - Usage: `gitlab.create_project internal-api-client public`
- `gitlab.upload_file`
  - Upload or update a text file in a GitLab repository.
  - Usage: `gitlab.upload_file root/internal-api-client /workspace/client.py client.py main "Add client.py"`
- `gitlab.get_file`
  - Read a file from a GitLab repository at a given ref.
  - Usage: `gitlab.get_file root/internal-api-client client.py main`
- `owncloud.list_dir`
  - List files in an ownCloud directory.
  - Usage: `owncloud.list_dir Documents 1`
- `owncloud.upload_file`
  - Upload a local file into ownCloud WebDAV.
  - Usage: `owncloud.upload_file /workspace/onboarding_notes_2.txt Documents/onboarding_notes_2.txt`
- `owncloud.download_file`
  - Download a file from ownCloud WebDAV.
  - Usage: `owncloud.download_file Documents/report.txt /workspace/report.txt`

Prefer these tools over ad-hoc curl commands when they match the task.
