from __future__ import annotations

from pathlib import Path
import sys

from common import owncloud_headers, owncloud_webdav_url, print_json, request_bytes


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: owncloud_upload_file.py <local-file> <remote-path>", file=sys.stderr)
        return 2

    local_file = Path(sys.argv[1].strip())
    remote_path = sys.argv[2].strip()
    if not local_file.is_file():
        print(f"local file not found: {local_file}", file=sys.stderr)
        return 1
    if not remote_path:
        print("remote path is required", file=sys.stderr)
        return 2

    status, body = request_bytes(
        "PUT",
        owncloud_webdav_url(remote_path),
        headers=owncloud_headers(content_type="application/octet-stream"),
        body=local_file.read_bytes(),
    )
    print_json({"status_code": status, "body": body.decode("utf-8", errors="replace")})
    return 0 if status in {200, 201, 204} else 1


if __name__ == "__main__":
    raise SystemExit(main())
