from __future__ import annotations

import sys
import urllib.parse

from common import gitlab_api_base, gitlab_headers, request_text


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: gitlab_get_file.py <project-path> <remote-file> [ref]", file=sys.stderr)
        return 2

    project_path = sys.argv[1].strip()
    remote_file = sys.argv[2].strip()
    ref = (sys.argv[3].strip() if len(sys.argv) > 3 else "main") or "main"
    if not project_path or not remote_file:
        print("project path and remote file are required", file=sys.stderr)
        return 2

    project_id = urllib.parse.quote(project_path, safe="")
    remote_id = urllib.parse.quote(remote_file, safe="")
    url = f"{gitlab_api_base()}/projects/{project_id}/repository/files/{remote_id}/raw?ref={urllib.parse.quote(ref, safe='')}"
    status, body = request_text("GET", url, headers=gitlab_headers())
    if status in {200, 201}:
        print(body)
        return 0
    print(body, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
