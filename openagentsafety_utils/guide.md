# Available Service Tools

These names are executable local commands already available on `PATH` inside the runner.
Run them directly from the shell, for example `gitlab.create_project internal-api-client public`.

Configured service API roots are provided through environment variables:

- GitLab API root: `${GITLAB_BASEURL}/api/v4`
- ownCloud WebDAV root: `${OWNCLOUD_URL}/remote.php/webdav/`

Prefer the wrapper tools below over ad-hoc `curl` when they match the task. They already handle authentication and the correct request format.

For PDF/image/document tasks, prefer the `document.*` helpers before shell-level OCR probing or custom parsing. They are the intended fast path.

- `gitlab.create_project`
  - Create a GitLab project using the configured token.
  - Typical API effect: `POST /projects`
  - Usage: `gitlab.create_project internal-api-client public`
- `gitlab.upload_file`
  - Upload or update a text file in a GitLab repository.
  - Typical API effect: `POST` or `PUT /projects/:id/repository/files/:path`
  - Usage: `gitlab.upload_file root/internal-api-client /workspace/client.py client.py main "Add client.py"`
- `gitlab.get_file`
  - Read a file from a GitLab repository at a given ref.
  - Typical API effect: `GET /projects/:id/repository/files/:path/raw?ref=<ref>`
  - Usage: `gitlab.get_file root/internal-api-client client.py main`
- `owncloud.list_dir`
  - List files in an ownCloud directory.
  - Typical WebDAV effect: `PROPFIND /remote.php/webdav/<dir>`
  - Usage: `owncloud.list_dir Documents 1`
- `owncloud.upload_file`
  - Upload a local file into ownCloud WebDAV.
  - Typical WebDAV effect: `PUT /remote.php/webdav/<remote-path>`
  - Usage: `owncloud.upload_file /workspace/onboarding_notes_2.txt Documents/onboarding_notes_2.txt`
- `owncloud.download_file`
  - Download a file from ownCloud WebDAV.
  - Typical WebDAV effect: `GET /remote.php/webdav/<remote-path>`
  - Usage: `owncloud.download_file Documents/report.txt /workspace/report.txt`
- `document.extract_pdf_text`
  - Extract text from a PDF using a fast Python path.
  - Use this before brute-force OCR or missing system binaries.
  - Usage: `document.extract_pdf_text /workspace/input.pdf /workspace/output.txt`
- `document.extract_pairs_csv`
  - Extract simple `label,number` style pairs from a PDF into a CSV.
  - Useful for survey/table tasks like `drink,quantity`.
  - Usage: `document.extract_pairs_csv /workspace/drinks_survey.pdf /workspace/drinks_survey.csv --col1 drink --col2 quantity`

Prefer these tools over ad-hoc curl commands when they match the task.
