# owncloud.list_dir

List entries under an ownCloud WebDAV directory.

## Usage

```bash
owncloud.list_dir Documents 1
```

Arguments are remote directory path and optional WebDAV depth.

## Environment

- `OWNCLOUD_URL`
- `OWNCLOUD_USERNAME`
- `OWNCLOUD_PASSWORD`
- Optional `OWNCLOUD_HOST_HEADER`

Aliases accepted by OpenART service resolution include `OWNCLOUD_BASEURL`, `OWNCLOUD_BASE_URL`, `OWNCLOUD_USER`, `OWNCLOUD_PASS`, and `SERVER_HOSTNAME`.

## Side Effects

Reads remote ownCloud metadata.
