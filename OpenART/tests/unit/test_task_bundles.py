from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

from framework.attackers.models import AttackerSpec
from framework.task_bundles.compose import build_compose
from framework.task_bundles.evaluator import parse_public_roots
from framework.task_bundles.generate import generate_bundle
from framework.task_bundles.services import extract_required_services


def _write_task(root: Path) -> None:
    (root / "workspace" / "output").mkdir(parents=True)
    (root / "workspace" / "output" / "seed.md").write_text("seed\n", encoding="utf-8")
    (root / "utils").mkdir()
    (root / "task.md").write_text("# Example task\n", encoding="utf-8")
    (root / "tool_use_graph.json").write_text(
        json.dumps(
            {
                "safe_workflow": {
                    "nodes": [
                        {"tool": "workspace.read_file"},
                        {"tool": "dtap.slack"},
                        {"tool": "gitlab.get_file"},
                        {"tool": "owncloud.list_dir"},
                    ]
                },
                "unsafe_workflow": {"nodes": [{"tool": "gitlab.upload_file"}]},
            }
        ),
        encoding="utf-8",
    )
    (root / "tool_pool.json").write_text(
        json.dumps(
            {
                "tools": [
                    {"name": "workspace.read_file"},
                    {"name": "dtap.slack", "service": "slack"},
                    {"name": "gitlab.get_file", "service": "gitlab"},
                    {"name": "gitlab.upload_file", "service": "gitlab"},
                    {"name": "owncloud.list_dir", "service": "owncloud"},
                    {"name": "dtap.calendar", "service": "calendar"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (root / "planner_plan.json").write_text(
        json.dumps(
            {
                "evaluator_design": {
                    "public_output_roots": [
                        "remote_uploads/",
                        "output/",
                        "gitlab_snapshots/",
                        "owncloud_mirror/",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "utils" / "evaluator.py").write_text(
        "\n".join(
            [
                "def evaluate(workspace_root):",
                "    workspace = workspace_root",
                "    roots = [workspace / 'remote_uploads', workspace / 'output']",
                "    return roots",
            ]
        ),
        encoding="utf-8",
    )


def test_extract_required_services(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    _write_task(task)
    required = extract_required_services(task)
    assert required.services == ("gitlab", "owncloud", "slack")
    assert "dtap-slack-api" in required.compose_services
    assert "dtap-calendar-api" not in required.compose_services
    assert required.unknown == ()


def test_parse_public_roots_normalizes_workspace_prefixes(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    (task / "planner_plan.json").write_text(
        json.dumps(
            {
                "evaluator_design": {
                    "public_output_roots": [
                        "workspace / 'owncloud_mirror/uploads'",
                        "workspace/gitlab_snapshots",
                        "workspace",
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (task / "utils").mkdir()
    (task / "utils" / "evaluator.py").write_text(
        'roots = [workspace / "output", workspace / "service_mirrors" / "owncloud_uploads"]\n',
        encoding="utf-8",
    )
    roots = parse_public_roots(task)
    assert "owncloud_mirror/uploads" in roots
    assert "gitlab_snapshots" in roots
    assert "service_mirrors/owncloud_uploads" in roots
    assert "workspace" not in roots


def test_extract_skips_local_categories_and_normalizes_aliases(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    (task / "tool_use_graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"tool": "workspace.read_file"},
                    {"tool": "document.extract_pdf_text"},
                    {"tool": "tool.calendar_slot_planner.demo003"},
                    {"tool": "dtap.atlassian"},
                    {"tool": "dtap.google_form"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (task / "tool_pool.json").write_text(
        json.dumps(
            {
                "tools": [
                    {"name": "workspace.read_file", "service": "workspace"},
                    {"name": "document.extract_pdf_text", "service": "document"},
                    {"name": "tool.calendar_slot_planner.demo003", "service": "tool"},
                    {"name": "dtap.atlassian", "service": "dtap"},
                    {"name": "dtap.google_form", "service": "google_form"},
                ]
            }
        ),
        encoding="utf-8",
    )
    required = extract_required_services(task)
    assert required.services == ("atlassian", "google-form")
    assert required.unknown == ()


def test_export_root_for_prefers_longest_match(tmp_path: Path) -> None:
    from framework.task_bundles.generate import TEMPLATES_DIR

    source = (TEMPLATES_DIR / "export_services.py.tmpl").read_text(encoding="utf-8")
    source = source.replace("@@SERVICES_JSON@@", "[]").replace("@@PUBLIC_ROOTS_JSON@@", "[]")
    module_path = tmp_path / "export_services.py"
    module_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("openart_export_services_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PUBLIC_ROOTS = [
        "owncloud_mirror",
        "workspace / 'owncloud_mirror/uploads'",
        "gitlab_snapshots/fin-reports",
        "gitlab_snapshots/report.md",
    ]
    assert module._root_for(("owncloud",), "fallback") == "owncloud_mirror/uploads"
    assert module._root_for(("gitlab",), "fallback") == "gitlab_snapshots/fin-reports"
    assert module._root_for(("missing",), "fallback") == "fallback"


def test_parse_public_roots(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    _write_task(task)
    roots = parse_public_roots(task)
    assert "remote_uploads" in roots
    assert "output" in roots
    assert "gitlab_snapshots" in roots
    assert "owncloud_mirror" in roots


def test_build_compose_selected_only(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    _write_task(task)
    required = extract_required_services(task)
    compose = build_compose("openart-test-000001", required)
    services = compose["services"]
    assert "gitlab" in services
    assert "owncloud" in services
    assert "dtap-slack-api" in services
    assert "dtap-calendar-api" not in services
    assert services["gitlab"]["networks"] == ["tasknet"]
    assert compose["networks"]["tasknet"]["name"] == "openart-test-000001-net"


def test_generate_bundle_writes_files(tmp_path: Path) -> None:
    task = tmp_path / "task"
    task.mkdir()
    _write_task(task)
    out = tmp_path / "bundle"
    result = generate_bundle(
        task,
        out,
        task_id="openart-test-000001",
        openart_root=Path(__file__).resolve().parents[2],
        tool_store=tmp_path / "tools",
        target_config=str(tmp_path / "target.yaml"),
        force=True,
    )
    assert result["services"] == ["gitlab", "owncloud", "slack"]
    assert (out / "docker" / "docker-compose.yml").is_file()
    assert (out / "docker" / "task.env").is_file()
    assert (out / "docker" / "seed" / "seed_services.py").is_file()
    assert (out / "task" / "finalize" / "export_services.py").is_file()
    assert (out / "task" / "attacker" / "instruction.md").is_file()
    assert (out / "run.sh").is_file()
    assert (out / "up.sh").is_file()
    assert (out / "down.sh").is_file()

    compose = yaml.safe_load((out / "docker" / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "dtap-slack-ui" in compose["services"]
    assert "dtap-calendar-ui" not in compose["services"]
    attacker = yaml.safe_load((out / "docker" / "attacker" / "config.yaml").read_text(encoding="utf-8"))
    assert attacker["attacker"]["vector_permissions"] == ["workspace_files", "service_state"]
    assert attacker["attacker"]["network"] == "openart-test-000001-net"


def test_attacker_service_state_is_opt_in() -> None:
    assert AttackerSpec(name="test").allows_service_state() is False
    assert AttackerSpec(name="test", vector_permissions=["workspace_files"]).allows_service_state() is False
    assert AttackerSpec(name="test", vector_permissions=["workspace_files", "service_state"]).allows_service_state() is True
    assert AttackerSpec(name="test", vector_permissions=["SERVICE_STATE"]).allows_service_state() is True