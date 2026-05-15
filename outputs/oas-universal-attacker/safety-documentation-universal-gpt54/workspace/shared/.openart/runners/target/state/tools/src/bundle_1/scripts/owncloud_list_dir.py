from __future__ import annotations

import sys

from common import list_propfind_entries, owncloud_headers, owncloud_webdav_url, print_json, request_text


def main() -> int:
    remote_dir = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    depth = (sys.argv[2].strip() if len(sys.argv) > 2 else "1") or "1"
    status, body = request_text(
        "PROPFIND",
        owncloud_webdav_url(remote_dir),
        headers=owncloud_headers(depth=depth),
    )
    payload = {"status_code": status}
    if status == 207:
        payload["entries"] = list_propfind_entries(body)
        print_json(payload)
        return 0
    payload["body"] = body
    print_json(payload)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
