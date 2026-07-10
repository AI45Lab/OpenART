from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALLER_PATH = REPO_ROOT / "openart-tools" / "registry.install" / "scripts" / "registry_install.py"


def _load_impl():
    module_name = "_openart_registry_install_impl"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, INSTALLER_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load registry installer from {INSTALLER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load_impl()

DEFAULT_MAX_FILES = _impl.DEFAULT_MAX_FILES
DEFAULT_MAX_TOTAL_BYTES = _impl.DEFAULT_MAX_TOTAL_BYTES
GitHubSelection = _impl.GitHubSelection
ValidationReport = _impl.ValidationReport

_github_api_json = _impl._github_api_json
_github_api_raw_bytes = _impl._github_api_raw_bytes


def _sync_test_hooks() -> None:
    _impl._github_api_json = _github_api_json
    _impl._github_api_raw_bytes = _github_api_raw_bytes


def source_url(record: Mapping[str, Any]) -> str:
    return _impl._source_url(record)


def parse_github_url(url: str) -> Any:
    return _impl.parse_github_url(url)


def download_github_selection(selection: Any, destination: Path, **kwargs: Any) -> None:
    _sync_test_hooks()
    return _impl.download_github_selection(selection, destination, **kwargs)


def prepare_downloaded_tool(tool_dir: Path, *, tool_name: str, registry_description: str, record: Mapping[str, Any] | None = None) -> Any:
    return _impl.prepare_downloaded_tool(
        tool_dir,
        tool_name=tool_name,
        registry_description=registry_description,
        record=record,
    )


def install_registry_record(record: Mapping[str, Any], tool_store_root: Path, **kwargs: Any) -> dict[str, Any]:
    _sync_test_hooks()
    return _impl.install_registry_record(record, tool_store_root, **kwargs)


def install_registry_records(records: Iterable[Mapping[str, Any]], tool_store_root: Path, **kwargs: Any) -> dict[str, Any]:
    _sync_test_hooks()
    return _impl.install_registry_records(records, tool_store_root, **kwargs)


def install_registry_tools(index_path: Path, identifiers: Iterable[str], tool_store_root: Path, **kwargs: Any) -> dict[str, Any]:
    _sync_test_hooks()
    return _impl.install_registry_tools(index_path, identifiers, tool_store_root, **kwargs)
