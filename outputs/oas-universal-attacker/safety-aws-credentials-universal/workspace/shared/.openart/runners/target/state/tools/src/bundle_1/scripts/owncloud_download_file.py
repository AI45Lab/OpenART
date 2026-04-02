from __future__ import annotations

import sys

from common import owncloud_headers, owncloud_webdav_url, request_bytes, write_bytes_file


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: owncloud_download_file.py <remote-path> <local-file>", file=sys.stderr)
        return 2

    remote_path = sys.argv[1].strip()
    local_file = sys.argv[2].strip()
    if not remote_path or not local_file:
        print("remote path and local file are required", file=sys.stderr)
        return 2

    status, body = request_bytes(
        "GET",
        owncloud_webdav_url(remote_path),
        headers=owncloud_headers(),
    )
    if status not in {200, 201}:
        print(body.decode("utf-8", errors="replace"), file=sys.stderr)
        return 1

    write_bytes_file(local_file, body)
    print(local_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
