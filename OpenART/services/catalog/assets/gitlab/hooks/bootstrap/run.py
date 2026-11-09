#!/usr/bin/env python3
"""Create a GitLab root user and personal access token for a bundle."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def read_value(path: Path, name: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    return ""


def write_value(path: Path, name: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith(f"{name}="):
            output.append(f"{name}={value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{name}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


RUBY = """
u = User.find_by_username('root')
unless u
  org = Organizations::Organization.first
  Users::CreateService.new(nil, {
    username: 'root',
    name: 'Administrator',
    email: 'root@example.com',
    password: ENV['OPENART_GITLAB_ROOT_PASSWORD'],
    password_confirmation: ENV['OPENART_GITLAB_ROOT_PASSWORD'],
    skip_confirmation: true,
    organization_id: org&.id,
  }).execute
  u = User.find_by_username('root')
end
u.personal_access_tokens.where(name: 'openart').destroy_all
t = u.personal_access_tokens.create!(name: 'openart', scopes: ['api'], expires_at: Date.today + 365)
puts t.token
"""


def main() -> int:
    bundle_dir = Path(env("OPENART_BUNDLE_DIR", os.getcwd())).resolve()
    env_file = Path(env("OPENART_TASK_ENV_FILE", str(bundle_dir / "docker" / "task.env")))
    compose_file = Path(env("OPENART_COMPOSE_FILE", str(bundle_dir / "docker" / "docker-compose.yml")))
    service = env("OPENART_SERVICE_NAME", "gitlab")
    password = read_value(env_file, "GITLAB_ROOT_PASSWORD")
    if not password:
        raise SystemExit("GITLAB_ROOT_PASSWORD is missing from task.env")

    compose = ["docker", "compose", "--env-file", str(env_file), "-f", str(compose_file)]

    for _ in range(360):
        try:
            check = subprocess.run(
                compose + ["exec", "-T", service, "curl", "-fsS", "http://localhost:8929/-/health"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            check = None
        if check is not None and check.returncode == 0:
            break
        time.sleep(5)
    else:
        raise SystemExit("GitLab did not become healthy")

    token = ""
    last_error = ""
    for _ in range(30):
        result = subprocess.run(
            compose
            + [
                "exec",
                "-T",
                "-e",
                f"OPENART_GITLAB_ROOT_PASSWORD={password}",
                service,
                "gitlab-rails",
                "runner",
                RUBY,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        if result.returncode == 0 and lines and len(lines[-1]) >= 20:
            token = lines[-1]
            break
        last_error = (result.stderr or result.stdout or "").strip()[-1000:]
        time.sleep(5)

    if not token:
        raise SystemExit(f"failed to create a GitLab access token: {last_error}")

    write_value(env_file, "GITLAB_ACCESS_TOKEN", token)
    print(json.dumps({"service": service, "token": "created"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())