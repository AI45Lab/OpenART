# owncloud.download_file

Download a remote ownCloud WebDAV file into the workspace.

## Usage

```bash
owncloud.download_file Documents/report.txt /workspace/report.txt
```

Arguments are remote WebDAV path and local destination path.

## Environment

- `OWNCLOUD_URL`
- `OWNCLOUD_USERNAME`
- `OWNCLOUD_PASSWORD`
- Optional `OWNCLOUD_HOST_HEADER`

Aliases accepted by OpenART service resolution include `OWNCLOUD_BASEURL`, `OWNCLOUD_BASE_URL`, `OWNCLOUD_USER`, `OWNCLOUD_PASS`, and `SERVER_HOSTNAME`.

## Side Effects

Reads a remote ownCloud file and writes a local workspace file.
