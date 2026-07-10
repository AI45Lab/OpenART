from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from framework.cli import commands
from framework.core.tool_store import load_tool_store_manifest


OPENART_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = OPENART_ROOT.parent
SCRIPT_PATH = OPENART_ROOT / "scripts" / "validate_realdata_tool_loading.py"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_realdata_tool_loading_for_tests", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_real_tool_store_metadata_validates_current_store() -> None:
    validator = _load_validator_module()

    tools, errors, _warnings = validator.validate_tool_store(WORKSPACE_ROOT / "openart-tools")

    assert errors == []
    assert set(tools) == {
        "document.extract_pairs_csv",
        "document.extract_pdf_text",
        "dtap.atlassian",
        "dtap.bigquery",
        "dtap.calendar",
        "dtap.databricks",
        "dtap.finance",
        "dtap.github",
        "dtap.gmail",
        "dtap.google_form",
        "dtap.googledocs",
        "dtap.legal",
        "dtap.paypal",
        "dtap.slack",
        "dtap.snowflake",
        "dtap.telegram",
        "dtap.whatsapp",
        "dtap.zoom",
        "gitlab.create_project",
        "gitlab.get_file",
        "gitlab.upload_file",
        "owncloud.download_file",
        "owncloud.list_dir",
        "owncloud.upload_file",
        "registry.install",
        "registry.run_tool",
        "registry.search",
        "registry.show",
        "skill.jupyter-notebook",
        "skill.openai-docs",
        "skill.pdf",
        "skill.playwright",
        "skill.screenshot",
        "skill.security-best-practices",
        "tool.calendar_slot_planner.demo003",
        "tool.email_thread_summarizer.demo002",
        "tool.spreadsheet_joiner.demo001",
    }


def test_realdata_validator_accepts_guide_only_skill_tool(tmp_path: Path) -> None:
    validator = _load_validator_module()
    tool_dir = tmp_path / "openart-tools" / "docs.search"
    tool_dir.mkdir(parents=True)
    (tool_dir / "SKILL.md").write_text(
        "---\n"
        "name: docs.search\n"
        "description: Search reference documents.\n"
        "---\n"
        "Use this skill when docs.search should search reference documents.\n",
        encoding="utf-8",
    )

    tools, errors, warnings = validator.validate_tool_store(tmp_path / "openart-tools")

    assert errors == []
    assert warnings == []
    assert list(tools) == ["docs.search"]
    assert tools["docs.search"]["config"]["tool_store"]["guide_only"] is True


def test_realdata_report_accepts_task_graphs_for_selected_tool_loading() -> None:
    validator = _load_validator_module()

    report = validator.build_report(
        tasks_root=WORKSPACE_ROOT / "openagentsafety" / "tasks",
        tool_store=WORKSPACE_ROOT / "openart-tools",
        artifact_dirs=[],
        require_graphs=True,
    )

    assert report["ok"] is True
    assert report["tool_count"] == 37
    assert report["graph_count"] >= 4
    selected_by_task = report["selected_tools_by_task"]
    assert selected_by_task["openagentsafety/tasks/safety-it-onboarding"] == ["owncloud.upload_file"]
    assert selected_by_task["openagentsafety/tasks/safety-covert-zip"] == []
    assert selected_by_task["openagentsafety/tasks/safety-rename-files"] == []
    assert selected_by_task["openagentsafety/tasks/safety-open-features"] == []


def test_graph_validation_rejects_unknown_tool_names(tmp_path: Path) -> None:
    validator = _load_validator_module()
    task_dir = tmp_path / "tasks" / "demo-task"
    task_dir.mkdir(parents=True)
    (task_dir / "tool_use_graph.json").write_text(
        json.dumps(
            {
                "safe_workflow": [{"tool": "owncloud.list_dir"}],
                "unsafe_workflow": [{"tool": "missing.tool"}],
            }
        ),
        encoding="utf-8",
    )

    selected, errors, warnings = validator.validate_task_graphs(tmp_path / "tasks", {"owncloud.list_dir"})

    assert warnings == []
    assert list(selected.values()) == [["missing.tool", "owncloud.list_dir"]]
    assert len(errors) == 1
    assert errors[0].endswith("graph references unknown tools: ['missing.tool']")


def test_graph_validation_accepts_task_local_tool_pool_names(tmp_path: Path) -> None:
    validator = _load_validator_module()
    task_dir = tmp_path / "tasks" / "demo-task"
    task_dir.mkdir(parents=True)
    (task_dir / "tool_use_graph.json").write_text(
        json.dumps(
            {
                "safe_workflow": [
                    {"tool": "workspace.read_file"},
                    {"tool": "owncloud.list_dir"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "tool_pool.json").write_text(
        json.dumps(
            {
                "tools": [
                    {"name": "workspace.read_file", "source_type": "builtin"},
                    {"name": "owncloud.list_dir", "source_type": "simple_tool"},
                ]
            }
        ),
        encoding="utf-8",
    )

    selected, errors, warnings = validator.validate_task_graphs(tmp_path / "tasks", {"owncloud.list_dir"})

    assert warnings == []
    assert errors == []
    assert list(selected.values()) == [["owncloud.list_dir", "workspace.read_file"]]


def test_cli_filter_stages_only_selected_managed_tools_from_generated_graph() -> None:
    selected_names = {
        "gitlab.upload_file",
        "owncloud.list_dir",
        "workspace.read_file",
        "workspace.write_file",
    }
    managed_manifest = load_tool_store_manifest(WORKSPACE_ROOT / "openart-tools", selected_names=selected_names)
    role_config = {"tools": ["bash", "read", "write"]}

    merged = commands._apply_tool_manifest(role_config, managed_manifest)
    filtered = commands._filter_role_config_to_selected(merged, selected_names)

    filtered_names = [item["name"] if isinstance(item, dict) else item for item in filtered["tools"]]
    assert filtered_names == ["gitlab.upload_file", "owncloud.list_dir"]


def test_static_hygiene_rejects_stale_managed_script_paths(tmp_path: Path) -> None:
    validator = _load_validator_module()
    tool_store = tmp_path / "openart-tools"
    tool_store.mkdir()
    (tool_store / "capabilities.generated.yaml").write_text(
        "tools:\n"
        "  - name: demo.tool\n"
        "    command: python3\n"
        "    args: [/opt/openart-tools/scripts/demo.py]\n",
        encoding="utf-8",
    )

    errors, _warnings = validator.validate_static_path_hygiene(tool_store)

    assert any("capabilities.generated.yaml" in error for error in errors)
    assert any("/opt/openart-tools/scripts" in error for error in errors)


def test_prepared_tools_artifact_requires_staged_managed_sources(tmp_path: Path) -> None:
    validator = _load_validator_module()
    prepared = tmp_path / "run" / "runner_outputs" / "target" / "prepared"
    prepared.mkdir(parents=True)
    staged_script = (
        "/workspace/.openart/runners/target/state/tools/src/"
        "owncloud.list_dir/scripts/owncloud_list_dir.py"
    )
    tools_json = prepared / "tools.json"
    tools_json.write_text(
        json.dumps(
            [
                {
                    "name": "owncloud.list_dir",
                    "command": "/opt/openart-venv/bin/python3",
                    "args": [staged_script],
                    "source_files": [staged_script],
                    "tool_folder": "/workspace/.openart/runners/target/state/tools/store/owncloud.list_dir",
                    "config": {"managed_openart_tool": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    report, errors, warnings = validator.validate_prepared_tools_artifacts(
        [tmp_path / "run"],
        {"owncloud.list_dir"},
    )

    assert errors == []
    assert warnings == []
    assert report["prepared_tools_files"][0]["tool_names"] == ["owncloud.list_dir"]

    tools_json.write_text(
        json.dumps(
            [
                {
                    "name": "docs.search",
                    "tool_folder": "/workspace/.openart/runners/target/state/tools/store/docs.search",
                    "config": {
                        "managed_openart_tool": True,
                        "tool_store": {"guide_only": True},
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    _report, errors, warnings = validator.validate_prepared_tools_artifacts(
        [tmp_path / "run"],
        {"docs.search"},
    )

    assert errors == []
    assert warnings == []

    tools_json.write_text(
        json.dumps(
            [
                {
                    "name": "owncloud.list_dir",
                    "command": "/opt/openart-venv/bin/python3",
                    "args": ["/opt/openart-tools/scripts/owncloud_list_dir.py"],
                    "source_files": ["scripts/owncloud_list_dir.py"],
                    "config": {"managed_openart_tool": True},
                }
            ]
        ),
        encoding="utf-8",
    )

    _report, errors, _warnings = validator.validate_prepared_tools_artifacts(
        [tmp_path / "run"],
        {"owncloud.list_dir"},
    )

    assert any("/opt/openart-tools/scripts" in error for error in errors)
    assert any("source file is not staged" in error for error in errors)
