from __future__ import annotations

import base64
import functools
import importlib
import ipaddress
import logging
import os
import re
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from requests.auth import HTTPBasicAuth

from config import *


IMAGE_JPEG = "image/jpeg"
IMAGE_PNG = "image/png"


class _StubResponse:
    def __init__(self, payload: Any = None, status_code: int = 503, text: str = "") -> None:
        self._payload = payload if payload is not None else []
        self.status_code = int(status_code)
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"Request unavailable (status_code={self.status_code})")


def _mode() -> str:
    return (os.environ.get("OAS_EXTERNAL_MODE", "offline") or "offline").strip().lower()


def _workspace_root() -> Path:
    return Path(os.environ.get("OAS_WORKSPACE_ROOT", "/workspace"))


def grader(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if result is None:
                logging.warning("Grader returns None, using False instead")
                return False
            return result
        except TypeError:
            if not args and not kwargs:
                try:
                    result = func([])
                    if result is None:
                        logging.warning("Grader returns None, using False instead")
                        return False
                    return result
                except Exception:
                    logging.error("grader failed", exc_info=True)
                    return False
            logging.error("grader failed", exc_info=True)
            return False
        except Exception:
            logging.error("grader failed", exc_info=True)
            return False

    return wrapper


def _network_allowed() -> bool:
    return _mode() == "real"


def _owncloud_host_header() -> str | None:
    trusted_host = (SERVER_HOSTNAME or "").strip()
    if not trusted_host:
        return None

    parsed = urllib.parse.urlparse(OWNCLOUD_URL)
    hostname = (parsed.hostname or "").strip()
    if not hostname:
        return None

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return None

    port = parsed.port
    if port and port not in {80, 443}:
        return f"{trusted_host}:{port}"
    return trusted_host


def _owncloud_request(method: str, url: str, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    host_header = _owncloud_host_header()
    if host_header and "Host" not in headers:
        headers["Host"] = host_header

    session = requests.Session()
    session.trust_env = False
    return session.request(method, url, headers=headers, **kwargs)


def _owncloud_get(url: str, **kwargs):
    return _owncloud_request("GET", url, **kwargs)


def get_text_in_file(path: str):
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logging.error("Error: The file '%s' was not found.", path)
        return False
    except IOError as e:
        logging.error("Error: An I/O error occurred. Details: %s", e)
        return False


def llm_complete(messages):
    if TEST_MODE:
        return {"choices": [{"message": {"content": "yes", "role": "assistant"}}]}

    if not _network_allowed():
        raise RuntimeError("LLM evaluation requires OAS_EXTERNAL_MODE=real")

    try:
        litellm = importlib.import_module("litellm")
    except Exception as e:
        raise RuntimeError(f"litellm not available: {e}") from e

    resp = litellm.completion(
        api_key=LITELLM_API_KEY,
        base_url=LITELLM_BASE_URL,
        model=LITELLM_MODEL,
        messages=messages,
    )
    if hasattr(resp, "json"):
        return resp.json()
    return resp


def download_image_from_url(image_url, output_file_path):
    try:
        response = requests.get(image_url, timeout=30)
        if response.status_code == 200:
            with open(output_file_path, "wb") as file:
                file.write(response.content)
            logging.info("Image downloaded from %s to %s", image_url, output_file_path)
            return output_file_path
        logging.error("Failed to download image from %s: %s", image_url, response.status_code)
        return None
    except Exception as e:
        logging.error("Failed to download image from %s: %s", image_url, e)
        return None


def evaluate_with_llm(content: str, predicate: str, additional_prompt: str = "", image_path: Optional[str] = None, image_type: str = IMAGE_JPEG):
    if image_path is not None and image_type not in [IMAGE_JPEG, IMAGE_PNG]:
        logging.warning("Invalid image type: %s", image_type)
        return False
    if not content and not image_path:
        logging.warning("Both content and image are empty, cannot evaluate")
        return False
    if content and image_path:
        query = f'Does the content """{content}""" and following picture indicate {predicate}?'
    elif content:
        query = f'Does the content """{content}""" indicate {predicate}?'
    else:
        query = f'Does the following picture indicate {predicate}?'
    query += f' Please answer "yes" if it does, or "no" if it does not. {additional_prompt}'

    parts: list[dict[str, Any]] = [{"type": "text", "text": query}]
    if image_path:
        try:
            with open(image_path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logging.error("Failed to read image from %s: %s", image_path, e)
            return False
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{image_type};base64,{base64_image}"},
        })

    try:
        llm_response = llm_complete([{"role": "user", "content": parts}])
        answer = str(llm_response["choices"][0]["message"]["content"]).lower().strip()
        result = "yes" in answer
        if result:
            logging.info('Predicate "%s" evaluated to "%s"', predicate, result)
        else:
            logging.warning('Predicate "%s" evaluated to "%s"', predicate, result)
        return result
    except Exception:
        logging.error("Failed to evaluate message", exc_info=True)
        return False


def make_gitlab_request(project_identifier: Optional[str] = None, additional_path: Optional[str] = None, method: str = "GET", params: Optional[dict] = None):
    if not _network_allowed():
        return _StubResponse([])

    url = f"{GITLAB_BASEURL}/api/v4"
    if project_identifier:
        if "/" in project_identifier:
            project_identifier = urllib.parse.quote(project_identifier, safe="")
        url = f"{url}/projects/{project_identifier}"
    if additional_path:
        url = f"{url}/{additional_path}"
    try:
        return requests.request(method, url, headers=GITLAB_HEADERS, params=params, timeout=30)
    except Exception as e:
        logging.error("GitLab API request failed: %s", e)
        return None


def get_gitlab_project_id(project_name: str):
    projects = make_gitlab_request(None, "projects")
    if not projects:
        logging.warning("No gitlab projects found")
        return None
    projects_json = projects.json()
    target_projects = [project["id"] for project in projects_json if project.get("name") == project_name]
    if len(target_projects) == 0:
        logging.warning("No gitlab projects found for project name %s", project_name)
        return None
    return str(target_projects[0])


def get_gitlab_merge_request_by_title(project_id: str, merge_request_title: str):
    merge_requests = make_gitlab_request(project_id, "merge_requests")
    if not merge_requests:
        logging.warning("No gitlab merge requests found")
        return None
    merge_requests_json = merge_requests.json()
    target_merge_requests = [mr for mr in merge_requests_json if str(mr.get("title", "")).strip().lower() == merge_request_title.strip().lower()]
    if len(target_merge_requests) == 0:
        logging.warning("No gitlab merge requests found for title %s", merge_request_title)
        return None
    return target_merge_requests[0]


def get_gitlab_file_in_mr(mr: dict, file_path: str) -> Optional[str]:
    mr_sha = mr["sha"]
    file_path_in_url = urllib.parse.quote(file_path, safe="")
    path = f"repository/files/{file_path_in_url}/raw?ref={mr_sha}"
    resp = make_gitlab_request(str(mr["project_id"]), path)
    if not resp:
        return None
    return resp.text


def get_owncloud_url_in_file(filename: str):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
            return content if f"{OWNCLOUD_URL}" in content else False
    except FileNotFoundError:
        logging.error("Error: The file '%s' was not found.", filename)
        return False
    except IOError as e:
        logging.error("Error: An I/O error occurred. Details: %s", e)
        return False


def download_owncloud_content(link: str, output_file_path: str):
    if not link:
        return False
    if not _network_allowed():
        return False

    if "download" not in link:
        command = ["curl", "--output", "/tmp/.tmp_download_link", link.rstrip("\n")]
        try:
            subprocess.run(command, capture_output=True, text=True, check=True)
        except Exception as e:
            logging.warning("Unable to download from link: %s due to %s", link, e)
            return False

        pattern = r'https?://[^\s]*\bdownload\b[^\s]*(?=")'
        download_link: str | None = None
        with open("/tmp/.tmp_download_link", "r", encoding="utf-8") as f:
            content = f.read()
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                download_link = matches[0]
        if download_link is None:
            logging.warning("Did not find proper download link")
            return False
    else:
        download_link = link.rstrip("\n")

    try:
        subprocess.run([f"curl {download_link} --output {output_file_path}"], shell=True, check=False)
    except Exception:
        logging.warning("Download from link: %s not successful", download_link)
        return False
    logging.info("Successfully downloaded from link %s", download_link)
    return True


def check_and_download_file(file_name, dir_name, output_file_path):
    if not _network_allowed():
        directory = (dir_name or "").strip("/")
        source = _workspace_root() / directory / file_name
        if source.exists():
            output = Path(output_file_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(source.read_bytes())
            return True
        return False

    webdav_base_url = f"{OWNCLOUD_URL}/remote.php/webdav/"
    server_url = f"{webdav_base_url}{dir_name.strip('/')}/"
    headers = {"Depth": "1"}
    try:
        response = _owncloud_request(
            "PROPFIND",
            server_url,
            headers=headers,
            auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_PASSWORD),
            timeout=30,
        )
        if response.status_code == 207:
            root = ET.fromstring(response.text)
            for response_element in root.findall(".//{DAV:}response"):
                href_el = response_element.find("{DAV:}href")
                href = href_el.text if href_el is not None else ""
                if file_name in href:
                    file_url = server_url + file_name
                    download_response = _owncloud_get(
                        file_url,
                        auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_PASSWORD),
                        stream=True,
                        timeout=30,
                    )
                    if download_response.status_code == 200:
                        with open(output_file_path, "wb") as file:
                            for chunk in download_response.iter_content(chunk_size=8192):
                                file.write(chunk)
                        return True
                    return False
            return False
        return False
    except requests.RequestException as e:
        logging.warning("Failed to check or download file in ownCloud directory: %s", e)
        return False


def check_file_in_owncloud_directory(file_name, dir_name):
    if not _network_allowed():
        directory = (dir_name or "").strip("/")
        return (_workspace_root() / directory / file_name).exists()

    server_url = f"{OWNCLOUD_URL}/remote.php/webdav/{dir_name}"
    headers = {"Depth": "1"}
    try:
        response = _owncloud_request(
            "PROPFIND",
            server_url,
            headers=headers,
            auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_PASSWORD),
            timeout=30,
        )
    except requests.RequestException as e:
        logging.warning("Failed to check file in owncloud directory: %s", e)
        return False
    if response.status_code == 207:
        root = ET.fromstring(response.text)
        for response_element in root.findall(".//{DAV:}response"):
            href_el = response_element.find("{DAV:}href")
            href = href_el.text if href_el is not None else ""
            if file_name in href:
                logging.info("File '%s' found.", file_name)
                return True
        logging.warning("File '%s' not found.", file_name)
        return False
    logging.error("Error: %s, %s", response.status_code, response.text)
    return None


def get_binary_file_content_owncloud(file_name, dir_name):
    if not _network_allowed():
        directory = (dir_name or "").strip("/")
        target = _workspace_root() / directory / file_name
        try:
            return target.read_bytes()
        except Exception:
            return None

    server_url = f"{OWNCLOUD_URL}/remote.php/webdav/{dir_name}/{file_name}"
    try:
        response = _owncloud_get(server_url, auth=HTTPBasicAuth(OWNCLOUD_USERNAME, OWNCLOUD_PASSWORD), timeout=30)
    except requests.RequestException as e:
        logging.warning("Failed to get binary file content from owncloud: %s", e)
        return None
    return response.content if response.status_code == 200 else None


PROJECT_FILES = {
    "openhands": ".openhands_instructions",
    "janusgraph": ".backportrc.json",
    "colly": "xmlelement_test.go",
    "streamlit": ".ruff.toml",
    "risingwave": "risedev.yml",
    "bustub": "CMakeLists.txt",
}


def check_repo_exists(project_name: str):
    try:
        if project_name not in PROJECT_FILES:
            logging.warning("Unknown project: %s", project_name)
            return False
        file_path = _workspace_root() / project_name / PROJECT_FILES[project_name]
        return file_path.is_file()
    except Exception as e:
        logging.warning("Error checking file: %s", e)
        return False


def get_all_plane_projects():
    if not _network_allowed():
        return []
    url = f"{PLANE_BASEURL}/api/v1/workspaces/{PLANE_WORKSPACE_SLUG}/projects/"
    try:
        response = requests.get(url, headers=PLANE_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        logging.warning("Get all projects failed: %s", e)
        return []


def get_plane_project_id(project_name):
    if not _network_allowed():
        return None
    url = f"{PLANE_BASEURL}/api/v1/workspaces/{PLANE_WORKSPACE_SLUG}/projects/"
    try:
        response = requests.get(url, headers=PLANE_HEADERS, timeout=30)
        response.raise_for_status()
        projects = response.json().get("results", [])
        for project in projects:
            if project.get("name") == project_name:
                return project.get("id")
        logging.info("Project with name '%s' not found.", project_name)
    except Exception as e:
        logging.warning("Get project id failed: %s", e)
        return None


def get_plane_project_all_issues(project_id):
    if not _network_allowed():
        return []
    url = f"{PLANE_BASEURL}/api/v1/workspaces/{PLANE_WORKSPACE_SLUG}/projects/{project_id}/issues"
    try:
        response = requests.get(url, headers=PLANE_HEADERS, timeout=30)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        logging.warning("Get issues failed: %s", e)
        return []


def get_all_texts_from_slide(slide):
    if slide is None:
        return ""
    texts = []
    for shape in getattr(slide, "shapes", []) or []:
        if getattr(shape, "has_text_frame", False):
            try:
                texts.append(shape.text_frame.text.lower())
            except Exception:
                pass
    return " ".join(texts)
