from __future__ import annotations

import os

# Lightweight evaluator config shim inspired by the upstream OpenAgentSafety
# base image design. We keep the same service-oriented environment surface,
# but we do not duplicate their full image/runtime.

TEST_MODE = (os.environ.get("TAC_TEST_MODE", "") or "").strip().lower() in {"1", "true", "yes"}

SERVER_HOSTNAME = os.environ.get("SERVER_HOSTNAME") or "100.100.194.4"

# LLM evaluator config
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY")
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "https://api.openai.com/v1")
LITELLM_MODEL = os.environ.get("LITELLM_MODEL", "gpt-4o")

# OwnCloud config
OWNCLOUD_PORT = os.environ.get("OWNCLOUD_PORT") or "8092"
OWNCLOUD_URL = os.environ.get("OWNCLOUD_URL") or f"http://{SERVER_HOSTNAME}:{OWNCLOUD_PORT}"
OWNCLOUD_USERNAME = os.environ.get("OWNCLOUD_USERNAME") or "theagentcompany"
OWNCLOUD_PASSWORD = os.environ.get("OWNCLOUD_PASSWORD") or "theagentcompany"

# GitLab config
GITLAB_PORT = os.environ.get("GITLAB_PORT") or "8929"
GITLAB_BASEURL = os.environ.get("GITLAB_BASEURL") or f"http://{SERVER_HOSTNAME}:{GITLAB_PORT}"
GITLAB_ACCESS_TOKEN = os.environ["GITLAB_ACCESS_TOKEN"] if "GITLAB_ACCESS_TOKEN" in os.environ else "glpat-wnMr_ZQpyy1c9-iaKJs2"
GITLAB_HEADERS = {"PRIVATE-TOKEN": GITLAB_ACCESS_TOKEN} if GITLAB_ACCESS_TOKEN else {}
GITLAB_USER = os.environ.get("GITLAB_USER") or "root"

# Plane config
PLANE_PORT = os.environ.get("PLANE_PORT") or "8091"
PLANE_BASEURL = os.environ.get("PLANE_BASEURL") or f"http://{SERVER_HOSTNAME}:{PLANE_PORT}"
PLANE_WORKSPACE_SLUG = os.environ.get("PLANE_WORKSPACE_SLUG") or "tac"
PLANE_API_KEY = os.environ.get("PLANE_API_KEY") or "plane_api_83f868352c6f490aba59b869ffdae1cf"
PLANE_HEADERS = {
    "x-api-key": PLANE_API_KEY,
    "Content-Type": "application/json",
}
