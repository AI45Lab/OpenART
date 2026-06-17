from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.core.tool_store import (
    ToolStoreError,
    load_tool_store_manifest,
    resolve_manifest_tool_env,
    selected_tool_names_from_task,
    tool_names_from_graph,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_tool_store_discovers_sibling_tools_and_reads_guides() -> None:
    manifest = load_tool_store_manifest(REPO_ROOT / "openart-tools", selected_names={"owncloud.upload_file"})

    assert [tool["name"] for tool in manifest["tools"]] == ["owncloud.upload_file"]
    tool = manifest["tools"][0]
    assert tool["tool_root"].endswith("openart-tools/owncloud.upload_file")
    assert tool["source_files"] == ["scripts/owncloud_upload_file.py", "scripts/common.py"]
    assert "owncloud.upload_file" in manifest["tool_guide_markdown"]


def test_tool_store_loads_registry_helper_tools() -> None:
    selected = {"registry.search", "registry.show", "registry.install", "registry.run_tool"}
    manifest = load_tool_store_manifest(REPO_ROOT / "openart-tools", selected_names=selected)

    names = {tool["name"] for tool in manifest["tools"]}
    assert names == selected
    by_name = {tool["name"]: tool for tool in manifest["tools"]}
    assert by_name["registry.search"]["source_files"] == ["scripts/registry_search.py"]
    assert by_name["registry.install"]["source_files"] == ["scripts/registry_install.py"]
    assert by_name["registry.install"]["capabilities"] == [
        "tool_registry_install",
        "local_tool_store_write",
    ]
    assert "registry.search" in manifest["tool_guide_markdown"]
    assert "registry.install" in manifest["tool_guide_markdown"]


def test_generated_tool_pool_includes_registry_helpers() -> None:
    selected = {"registry.search", "registry.show", "registry.install", "registry.run_tool"}
    pool = json.loads((REPO_ROOT / "openart-tools" / "tool_pool.json").read_text(encoding="utf-8"))

    by_name = {tool["name"]: tool for tool in pool["tools"]}
    assert selected <= set(by_name)
    deleted_helper = "registry." + "materialize"
    assert deleted_helper not in by_name
    assert all(by_name[name]["ready"] is True for name in selected)
    assert pool["capability_groups"]["tool_registry_search"] == ["registry.search"]
    assert pool["capability_groups"]["tool_registry_install"] == ["registry.install"]
    assert "registry.install" in pool["capability_groups"]["local_tool_store_write"]


def test_deleted_registry_helper_is_absent() -> None:
    deleted_helper = "registry." + "materialize"
    assert not (REPO_ROOT / "openart-tools" / deleted_helper).exists()
    assert deleted_helper not in (REPO_ROOT / "openart-tools" / "tool_pool.json").read_text(encoding="utf-8")
    assert deleted_helper not in (REPO_ROOT / "openart-tools" / "capabilities.generated.yaml").read_text(encoding="utf-8")
    for path in [
        REPO_ROOT / "README.md",
        REPO_ROOT / "OpenART" / "README.md",
        REPO_ROOT / "openart-tools" / "README.md",
    ]:
        assert deleted_helper not in path.read_text(encoding="utf-8")


def test_tool_store_prefers_skill_markdown_over_tool_markdown(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.publish"
    scripts = tool_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (tool_dir / "TOOL.md").write_text("# Legacy Guide\nUse the legacy guide.\n", encoding="utf-8")
    (tool_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo.publish\n"
        "description: Publish approved demo files.\n"
        "---\n"
        "Use this skill when approved demo files need to be published.\n",
        encoding="utf-8",
    )
    (tool_dir / "tool.yaml").write_text(
        "name: demo.publish\n"
        "command: python3\n"
        "args: [scripts/run.py]\n"
        "source_files: [scripts/run.py]\n",
        encoding="utf-8",
    )

    manifest = load_tool_store_manifest(tmp_path)

    tool = manifest["tools"][0]
    assert tool["description"] == "Publish approved demo files."
    assert tool["config"]["tool_store"]["guide_file"] == "SKILL.md"
    assert tool["config"]["tool_store"]["guide_only"] is False
    assert "approved demo files need to be published" in manifest["tool_guide_markdown"]
    assert "Legacy Guide" not in manifest["tool_guide_markdown"]


def test_tool_store_accepts_guide_only_tool_without_tool_yaml(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.search"
    tool_dir.mkdir()
    (tool_dir / "skills.md").write_text(
        "---\n"
        "name: demo.search\n"
        "description: Search demo reference material.\n"
        "---\n"
        "Use this skill when demo reference material needs to be searched.\n",
        encoding="utf-8",
    )

    manifest = load_tool_store_manifest(tmp_path)

    tool = manifest["tools"][0]
    assert tool["name"] == "demo.search"
    assert tool["description"] == "Search demo reference material."
    assert "command" not in tool
    assert "source_files" not in tool
    assert tool["config"]["tool_store"] == {
        "name": "demo.search",
        "source_files": [],
        "guide_file": "skills.md",
        "guide_only": True,
    }


def test_tool_store_accepts_lowercase_plural_tool_guide_without_tool_yaml(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.review"
    tool_dir.mkdir()
    (tool_dir / "tools.md").write_text(
        "# demo.review\n\nReview demo material and summarize findings.\n",
        encoding="utf-8",
    )

    manifest = load_tool_store_manifest(tmp_path)

    tool = manifest["tools"][0]
    assert tool["name"] == "demo.review"
    assert tool["description"] == "Review demo material and summarize findings."
    assert tool["config"]["tool_store"]["guide_file"] == "tools.md"
    assert tool["config"]["tool_store"]["guide_only"] is True


@pytest.mark.parametrize(
    ("skill_text", "expected"),
    [
        ("name: demo.tool\nUse this skill when demo work is needed.\n", "missing YAML frontmatter"),
        (
            "---\nname: other.tool\ndescription: Demo tool.\n---\nUse this skill when demo work is needed.\n",
            "must match tool name",
        ),
        (
            "---\nname: demo.tool\n---\nUse this skill when demo work is needed.\n",
            "frontmatter requires non-empty description",
        ),
        ("---\nname: demo.tool\ndescription: Demo tool.\n---\n", "requires non-empty Markdown body"),
        (
            "---\nname: demo.tool\ndescription: Demo tool.\n---\nThis wraps the tool.\n",
            "missing activation cue",
        ),
    ],
)
def test_tool_store_rejects_invalid_skill_markdown(tmp_path: Path, skill_text: str, expected: str) -> None:
    tool_dir = tmp_path / "demo.tool"
    tool_dir.mkdir()
    (tool_dir / "SKILL.md").write_text(skill_text, encoding="utf-8")

    with pytest.raises(ToolStoreError, match=expected):
        load_tool_store_manifest(tmp_path)


def test_tool_store_rejects_missing_source_files(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.tool"
    tool_dir.mkdir()
    (tool_dir / "TOOL.md").write_text("# demo.tool\n", encoding="utf-8")
    (tool_dir / "tool.yaml").write_text(
        "name: demo.tool\ncommand: python3\nargs: [scripts/run.py]\n",
        encoding="utf-8",
    )

    with pytest.raises(ToolStoreError, match="source_files"):
        load_tool_store_manifest(tmp_path)


def test_tool_store_rejects_path_traversal_source_files(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.tool"
    tool_dir.mkdir()
    (tool_dir / "TOOL.md").write_text("# demo.tool\n", encoding="utf-8")
    (tool_dir / "tool.yaml").write_text(
        "name: demo.tool\ncommand: python3\nargs: [scripts/run.py]\nsource_files: [../run.py]\n",
        encoding="utf-8",
    )

    with pytest.raises(ToolStoreError, match="invalid source_files path"):
        load_tool_store_manifest(tmp_path)


def test_tool_store_rejects_absolute_managed_script_args(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.tool"
    scripts = tool_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (tool_dir / "TOOL.md").write_text("# demo.tool\n", encoding="utf-8")
    (tool_dir / "tool.yaml").write_text(
        "name: demo.tool\n"
        "command: /opt/openart-venv/bin/python3\n"
        "args: [/opt/openart-tools/scripts/run.py]\n"
        "source_files: [scripts/run.py]\n",
        encoding="utf-8",
    )

    with pytest.raises(ToolStoreError, match="managed tool script paths must be relative"):
        load_tool_store_manifest(tmp_path)


def test_tool_store_full_load_skips_invalid_quarantine_folders(tmp_path: Path) -> None:
    invalid = tmp_path / ".invalid.demo.tool"
    invalid.mkdir()
    (invalid / "SKILL.md").write_text("not valid skill frontmatter\n", encoding="utf-8")
    invalid_suffix = tmp_path / "demo.tool.invalid.123"
    invalid_suffix.mkdir()
    (invalid_suffix / "tool.yaml").write_text("name: demo.tool\n", encoding="utf-8")
    (invalid_suffix / "TOOL.md").write_text("# demo.tool\n", encoding="utf-8")
    valid = tmp_path / "demo.tool"
    scripts = valid / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (valid / "TOOL.md").write_text("# demo.tool\n\nRun the demo tool.\n", encoding="utf-8")
    (valid / "tool.yaml").write_text(
        "name: demo.tool\ncommand: python3\nargs: [scripts/run.py]\nsource_files: [scripts/run.py]\n",
        encoding="utf-8",
    )

    manifest = load_tool_store_manifest(tmp_path)

    assert [tool["name"] for tool in manifest["tools"]] == ["demo.tool"]


def test_resolve_manifest_tool_env_copies_host_alias_to_canonical_key(tmp_path: Path) -> None:
    tool_dir = tmp_path / "demo.service"
    scripts = tool_dir / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (tool_dir / "TOOL.md").write_text("# demo.service\n\nRun service demo.\n", encoding="utf-8")
    (tool_dir / "tool.yaml").write_text(
        "name: demo.service\n"
        "command: python3\n"
        "args: [scripts/run.py]\n"
        "source_files: [scripts/run.py]\n"
        "required_env:\n"
        "  DEMO_TOKEN:\n"
        "    aliases: [LEGACY_DEMO_TOKEN]\n",
        encoding="utf-8",
    )
    manifest = load_tool_store_manifest(tmp_path)

    resolved, runtime_env = resolve_manifest_tool_env(manifest, {"LEGACY_DEMO_TOKEN": "secret"})

    tool_env = resolved["tools"][0]["env"]
    assert tool_env["DEMO_TOKEN"] == "secret"
    assert tool_env["LEGACY_DEMO_TOKEN"] == "secret"
    assert runtime_env["DEMO_TOKEN"] == "secret"


def test_tool_graph_selector_collects_safe_unsafe_and_hidden_workflows(tmp_path: Path) -> None:
    graph = {
        "safe_workflow": [{"tool": "owncloud.upload_file"}],
        "unsafe_workflow": {"nodes": [{"tool": "gitlab.get_file"}]},
        "oracle_workflow": {"nested": {"tool": "document.extract_pdf_text"}},
        "hidden": [{"steps": [{"tool": "owncloud.download_file"}]}],
    }
    assert tool_names_from_graph(graph) == {
        "owncloud.upload_file",
        "gitlab.get_file",
        "document.extract_pdf_text",
        "owncloud.download_file",
    }

    (tmp_path / "tool_use_graph.json").write_text(json.dumps(graph), encoding="utf-8")
    assert selected_tool_names_from_task(tmp_path) == tool_names_from_graph(graph)
