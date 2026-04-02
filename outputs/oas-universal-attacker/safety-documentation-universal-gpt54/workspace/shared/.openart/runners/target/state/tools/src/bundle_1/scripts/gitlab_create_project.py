from __future__ import annotations

import sys

from common import gitlab_api_base, gitlab_headers, print_json, request_text, urlencode_payload


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: gitlab_create_project.py <project-name> [visibility]", file=sys.stderr)
        return 2

    project_name = sys.argv[1].strip()
    visibility = (sys.argv[2].strip() if len(sys.argv) > 2 else "public") or "public"
    if not project_name:
        print("project name is required", file=sys.stderr)
        return 2

    status, body = request_text(
        "POST",
        gitlab_api_base() + "/projects",
        headers=gitlab_headers(form=True),
        body=urlencode_payload({"name": project_name, "visibility": visibility}),
    )
    print_json({"status_code": status, "body": body})
    return 0 if status in {200, 201} else 1


if __name__ == "__main__":
    raise SystemExit(main())
