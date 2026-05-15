from __future__ import annotations

from pathlib import Path
import sys
import urllib.parse

from common import gitlab_api_base, gitlab_headers, print_json, request_text, urlencode_payload


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: gitlab_upload_file.py <project-path> <local-file> [remote-file] [branch] [commit-message]",
            file=sys.stderr,
        )
        return 2

    project_path = sys.argv[1].strip()
    local_file = Path(sys.argv[2].strip())
    remote_file = (sys.argv[3].strip() if len(sys.argv) > 3 else local_file.name) or local_file.name
    branch = (sys.argv[4].strip() if len(sys.argv) > 4 else "main") or "main"
    commit_message = (sys.argv[5].strip() if len(sys.argv) > 5 else f"Add {remote_file}") or f"Add {remote_file}"

    if not project_path:
        print("project path is required", file=sys.stderr)
        return 2
    if not local_file.is_file():
        print(f"local file not found: {local_file}", file=sys.stderr)
        return 1

    project_id = urllib.parse.quote(project_path, safe="")
    remote_id = urllib.parse.quote(remote_file, safe="")
    url = f"{gitlab_api_base()}/projects/{project_id}/repository/files/{remote_id}"
    payload = {
        "branch": branch,
        "commit_message": commit_message,
        "content": local_file.read_text(encoding="utf-8"),
    }

    status, body = request_text(
        "POST",
        url,
        headers=gitlab_headers(form=True),
        body=urlencode_payload(payload),
    )
    if status not in {200, 201}:
        status, body = request_text(
            "PUT",
            url,
            headers=gitlab_headers(form=True),
            body=urlencode_payload(payload),
        )

    print_json({"status_code": status, "body": body})
    return 0 if status in {200, 201} else 1


if __name__ == "__main__":
    raise SystemExit(main())
