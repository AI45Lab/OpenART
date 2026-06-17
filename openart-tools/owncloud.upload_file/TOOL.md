# owncloud.upload_file

Upload a local file into ownCloud through WebDAV.

## Usage

```bash
owncloud.upload_file /workspace/onboarding_notes_2.txt Documents/onboarding_notes_2.txt
```

Arguments are local file path and remote WebDAV path.

## Environment

- `OWNCLOUD_URL`
- `OWNCLOUD_USERNAME`
- `OWNCLOUD_PASSWORD`
- Optional `OWNCLOUD_HOST_HEADER`

Aliases accepted by OpenART service resolution include `OWNCLOUD_BASEURL`, `OWNCLOUD_BASE_URL`, `OWNCLOUD_USER`, `OWNCLOUD_PASS`, and `SERVER_HOSTNAME`.

## Side Effects

Writes a remote ownCloud file.
