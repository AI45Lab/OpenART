from __future__ import annotations

import base64
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from framework.core.tool_store import load_tool_store_manifest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_registry_install_module():
    path = REPO_ROOT / "openart-tools" / "registry.install" / "scripts" / "registry_install.py"
    spec = importlib.util.spec_from_file_location("registry_install_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


registry_install = _load_registry_install_module()


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _make_index(tmp_path: Path) -> Path:
    index = tmp_path / "tool_registry.sqlite"
    conn = sqlite3.connect(index)
    conn.execute(
        """
        CREATE TABLE tools (
            tool_id TEXT PRIMARY KEY,
            virtual_tool_name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            source_url TEXT NOT NULL,
            raw TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.commit()
    conn.close()
    return index


def _add_row(
    index: Path,
    *,
    tool_id: str,
    tool_name: str | None = None,
    description: str = "Installable registry guide.",
    source_url: str = "https://github.com/acme/tools/tree/main/skills/demo",
    raw: dict[str, object] | None = None,
) -> str:
    name = tool_name or tool_id
    conn = sqlite3.connect(index)
    conn.execute(
        """
        INSERT INTO tools(tool_id, virtual_tool_name, description, source_url, raw, deleted_at)
        VALUES (?, ?, ?, ?, ?, '')
        """,
        (tool_id, name, description, source_url, json.dumps(raw or {})),
    )
    conn.commit()
    conn.close()
    return name


def _mock_github_api(_selection, api_path: str):
    responses = {
        "skills/demo": [
            {"type": "file", "path": "skills/demo/SKILL.md"},
            {"type": "file", "path": "skills/demo/tool.yaml"},
            {"type": "dir", "path": "skills/demo/scripts"},
        ],
        "skills/demo/SKILL.md": {
            "type": "file",
            "path": "skills/demo/SKILL.md",
            "encoding": "base64",
            "content": _b64("---\nname: upstream-demo\n---\n# Demo Guide\nRead the upstream notes.\n"),
        },
        "skills/demo/tool.yaml": {
            "type": "file",
            "path": "skills/demo/tool.yaml",
            "encoding": "base64",
            "content": _b64("name: upstream-demo\ncommand: python3\n"),
        },
        "skills/demo/scripts": [
            {"type": "file", "path": "skills/demo/scripts/run.py"},
        ],
        "skills/demo/scripts/run.py": {
            "type": "file",
            "path": "skills/demo/scripts/run.py",
            "encoding": "base64",
            "content": _b64("print('reference only')\n"),
        },
    }
    return responses[api_path]


def _write_valid_guide(tool_store: Path, tool_name: str, marker: str = "") -> Path:
    tool_dir = tool_store / tool_name
    tool_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {tool_name}\n"
        "description: Existing guide.\n"
        "---\n"
        f"Use this skill when `{tool_name}` is selected for registry-backed work.\n"
        f"{marker}\n",
        encoding="utf-8",
    )
    return tool_dir


def test_url_resolution_and_github_url_rejection() -> None:
    assert registry_install._source_url(
        {
            "source_url": "https://github.com/acme/tools/tree/main/skills/demo",
            "raw": {"record": {"skill_url": "https://github.com/acme/other/tree/main/skill"}},
        }
    ) == "https://github.com/acme/tools/tree/main/skills/demo"
    assert registry_install._source_url(
        {
            "source_url": "",
            "raw": {"record": {"skill_url": "https://github.com/acme/tools/blob/main/SKILL.md"}},
        }
    ) == "https://github.com/acme/tools/blob/main/SKILL.md"

    parsed = registry_install.parse_github_url("https://github.com/acme/tools/tree/main/skills/demo")
    assert (parsed.owner, parsed.repo, parsed.kind, parsed.ref, parsed.path) == ("acme", "tools", "tree", "main", "skills/demo")

    with pytest.raises(ValueError, match="only https://github.com"):
        registry_install.parse_github_url("https://example.com/acme/tools/tree/main/skills/demo")
    with pytest.raises(ValueError, match="plain repo URLs"):
        registry_install.parse_github_url("https://github.com/acme/tools")


def test_registry_install_downloads_normalizes_and_loads_guide_only_tool(monkeypatch, tmp_path: Path) -> None:
    index = _make_index(tmp_path)
    tool_name = _add_row(index, tool_id="tool.demo.fixture001", description="Registry row description.")
    tool_store = tmp_path / "openart-tools"
    monkeypatch.setattr(registry_install, "_github_api_json", _mock_github_api)

    summary = registry_install.install_registry_tools(index, [tool_name], tool_store)

    assert [item["tool_name"] for item in summary["created"]] == [tool_name]
    tool_dir = tool_store / tool_name
    assert tool_dir.is_dir()
    assert not (tool_dir / "tool.yaml").exists()
    assert not (tool_dir / "scripts" / "registry_run_tool.py").exists()
    assert (tool_dir / "scripts" / "run.py").read_text(encoding="utf-8") == "print('reference only')\n"
    assert (tool_dir / "references" / "original_tool.yaml").is_file()
    assert (tool_dir / "references" / "original_SKILL.md").is_file()

    skill_text = (tool_dir / "SKILL.md").read_text(encoding="utf-8")
    assert f"name: {tool_name}" in skill_text
    assert "description: Registry row description." in skill_text
    assert "Use this skill when the OpenART registry selects" in skill_text

    manifest = load_tool_store_manifest(tool_store, selected_names={tool_name})
    tool = manifest["tools"][0]
    assert tool["name"] == tool_name
    assert "command" not in tool
    assert "source_files" not in tool
    assert tool["config"]["tool_store"]["guide_only"] is True


def test_registry_install_enforces_download_limits(monkeypatch, tmp_path: Path) -> None:
    index = _make_index(tmp_path)
    tool_name = _add_row(index, tool_id="tool.demo.fixture002")
    monkeypatch.setattr(registry_install, "_github_api_json", _mock_github_api)

    summary = registry_install.install_registry_tools(
        index,
        [tool_name],
        tmp_path / "openart-tools",
        max_files=1,
    )

    assert summary["created"] == []
    assert summary["failed"][0]["tool_name"] == tool_name
    assert "max-files=1" in summary["failed"][0]["reason"]


def test_registry_install_rejects_downloaded_path_traversal(monkeypatch, tmp_path: Path) -> None:
    index = _make_index(tmp_path)
    tool_name = _add_row(index, tool_id="tool.demo.fixture003")

    def unsafe_api(_selection, api_path: str):
        if api_path == "skills/demo":
            return [{"type": "file", "path": "skills/demo/../bad.md"}]
        return {
            "type": "file",
            "path": "skills/demo/../bad.md",
            "encoding": "base64",
            "content": _b64("bad\n"),
        }

    monkeypatch.setattr(registry_install, "_github_api_json", unsafe_api)

    summary = registry_install.install_registry_tools(index, [tool_name], tmp_path / "openart-tools")

    assert summary["failed"][0]["tool_name"] == tool_name
    assert "unsafe path" in summary["failed"][0]["reason"]


def test_registry_install_reports_unsupported_missing_and_plain_repo_urls(tmp_path: Path) -> None:
    index = _make_index(tmp_path)
    missing = _add_row(index, tool_id="tool.demo.missingurl", source_url="", raw={})
    non_github = _add_row(index, tool_id="tool.demo.nongithub", source_url="https://example.com/acme/tools/tree/main/skill")
    plain_repo = _add_row(index, tool_id="tool.demo.plainrepo", source_url="https://github.com/acme/tools")

    summary = registry_install.install_registry_tools(index, [missing, non_github, plain_repo], tmp_path / "openart-tools")

    assert summary["created"] == []
    assert {item["tool_name"] for item in summary["unsupported"]} == {missing, non_github, plain_repo}
    reasons = " ".join(item["reason"] for item in summary["unsupported"])
    assert "no source_url" in reasons
    assert "only https://github.com" in reasons
    assert "plain repo URLs" in reasons


def test_registry_install_existing_folder_reuse_replace_invalid_and_overwrite(monkeypatch, tmp_path: Path) -> None:
    index = _make_index(tmp_path)
    reused = _add_row(index, tool_id="tool.demo.reused", source_url="https://github.com/acme/tools")
    invalid = _add_row(index, tool_id="tool.demo.invalid")
    overwritten = _add_row(index, tool_id="tool.demo.overwrite")
    tool_store = tmp_path / "openart-tools"
    _write_valid_guide(tool_store, reused, marker="reuse sentinel")
    invalid_dir = tool_store / invalid
    invalid_dir.mkdir(parents=True)
    invalid_dir.joinpath("SKILL.md").write_text("not frontmatter\n", encoding="utf-8")
    _write_valid_guide(tool_store, overwritten, marker="overwrite sentinel")
    monkeypatch.setattr(registry_install, "_github_api_json", _mock_github_api)

    reuse_summary = registry_install.install_registry_tools(index, [reused], tool_store)
    assert [item["tool_name"] for item in reuse_summary["reused"]] == [reused]
    assert "reuse sentinel" in (tool_store / reused / "SKILL.md").read_text(encoding="utf-8")

    failed_summary = registry_install.install_registry_tools(index, [invalid], tool_store)
    assert failed_summary["failed"][0]["tool_name"] == invalid
    assert "--replace-invalid" in failed_summary["failed"][0]["reason"]
    assert not list(tool_store.glob(f"{invalid}.invalid.*"))

    replaced_summary = registry_install.install_registry_tools(index, [invalid], tool_store, replace_invalid=True)
    assert [item["tool_name"] for item in replaced_summary["created"]] == [invalid]
    assert list(tool_store.glob(f"{invalid}.invalid.*"))

    overwrite_summary = registry_install.install_registry_tools(index, [overwritten], tool_store, overwrite=True)
    assert [item["tool_name"] for item in overwrite_summary["created"]] == [overwritten]
    assert overwrite_summary["created"][0]["reason"] == "overwrote_existing"
    assert "overwrite sentinel" not in (tool_store / overwritten / "SKILL.md").read_text(encoding="utf-8")


def test_registry_install_cli_reports_created_reused_unsupported_and_failed(monkeypatch, capsys, tmp_path: Path) -> None:
    index = _make_index(tmp_path)
    created = _add_row(index, tool_id="tool.demo.cli_created")
    reused = _add_row(index, tool_id="tool.demo.cli_reused", source_url="https://github.com/acme/tools")
    unsupported = _add_row(index, tool_id="tool.demo.cli_unsupported", source_url="https://github.com/acme/tools")
    failed = _add_row(index, tool_id="tool.demo.cli_failed")
    tool_store = tmp_path / "openart-tools"
    _write_valid_guide(tool_store, reused)
    failed_dir = tool_store / failed
    failed_dir.mkdir(parents=True)
    failed_dir.joinpath("SKILL.md").write_text("not frontmatter\n", encoding="utf-8")
    monkeypatch.setattr(registry_install, "_github_api_json", _mock_github_api)

    exit_code = registry_install.main(
        [
            "--index",
            str(index),
            "--ids",
            created,
            reused,
            unsupported,
            failed,
            "--tool-store",
            str(tool_store),
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 1
    assert f"CREATED: {created}" in out
    assert f"REUSED: {reused}" in out
    assert f"UNSUPPORTED: {unsupported}" in out
    assert f"FAILED: {failed}" in out
