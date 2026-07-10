from __future__ import annotations

import json
import base64
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from framework.core.tool_store import load_tool_store_manifest
from framework.planner import opencode_backend
from framework.planner import registry as planner_registry
from framework.planner.cli import build_parser


def _registry_path(tool_store: Path) -> Path:
    return tool_store / ".registry" / "openart_tool_registry.sqlite"


def _add_registry_tool(
    tool_store: Path,
    *,
    name: str = "PDF Text Extractor",
    description: str = "Extract text from PDF reports.",
    capabilities: list[str] | None = None,
    include_openart_tool: bool = True,
    source_url: str = "",
    raw_extra: dict[str, object] | None = None,
) -> str:
    index = _registry_path(tool_store)
    index.parent.mkdir(parents=True, exist_ok=True)
    public_id = f"tool.{name.lower().replace(' ', '_')}.fixture123"
    conn = sqlite3.connect(index)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tools (
            tool_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            virtual_tool_name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT NOT NULL,
            stars INTEGER NOT NULL,
            evaluation TEXT NOT NULL,
            tags TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            raw TEXT NOT NULL,
            ready INTEGER NOT NULL DEFAULT 1,
            ready_mode TEXT NOT NULL DEFAULT 'instruction_lookup',
            deleted_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            user_notes TEXT NOT NULL DEFAULT ''
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS tools_fts USING fts5(
            tool_id UNINDEXED,
            virtual_tool_name UNINDEXED,
            display_name,
            description,
            category,
            evaluation_reasons,
            tags,
            capabilities,
            user_notes
        );
        """
    )
    caps = capabilities or ["document_processing", "pdf"]
    tags = ["pdf", "report"]
    openart_payload: dict[str, object] = dict(raw_extra or {})
    if include_openart_tool:
        tool_yaml = {
            "name": f"tool.{name.lower().replace(' ', '_')}.fixture123",
            "description": description,
            "command": "/opt/openart-venv/bin/python3",
            "args": ["scripts/materialize_stub.py"],
            "source_files": ["scripts/materialize_stub.py"],
            "capabilities": caps,
            "side_effects": ["local_file_read", "local_file_write"],
        }
        guide_markdown = (
            "---\n"
            f"name: {tool_yaml['name']}\n"
            f"description: {description}\n"
            "---\n"
            "Use this skill when the task requires this materialized registry tool.\n"
        )
        files = [
            {"path": "scripts/materialize_stub.py", "content": "if __name__ == \"__main__\":\n    print('materialized tool executed')\n"},
        ]
        openart_payload = {
            "openart_tool": {
                "tool_yaml": tool_yaml,
                "guide_file": "SKILLS.md",
                "guide_markdown": guide_markdown,
                "files": files,
            }
        }

    caps = capabilities or ["document_processing", "pdf"]
    row = {
        "tool_id": public_id,
        "name": name,
        "display_name": name,
        "virtual_tool_name": public_id,
        "description": description,
        "source": "fixture",
        "source_url": source_url,
        "author": "",
        "category": "document",
        "stars": 3,
        "evaluation": "{}",
        "tags": json.dumps(tags),
        "capabilities": json.dumps(caps),
        "raw": json.dumps(openart_payload),
        "ready": 1,
        "ready_mode": "instruction_lookup",
        "deleted_at": "",
        "updated_at": "2026-06-12T00:00:00Z",
        "user_notes": "",
    }
    conn.execute(
        """
        INSERT INTO tools (
            tool_id, name, display_name, virtual_tool_name, description, source,
            source_url, author, category, stars, evaluation, tags, capabilities,
            raw, ready, ready_mode, deleted_at, updated_at, user_notes
        ) VALUES (
            :tool_id, :name, :display_name, :virtual_tool_name, :description, :source,
            :source_url, :author, :category, :stars, :evaluation, :tags, :capabilities,
            :raw, :ready, :ready_mode, :deleted_at, :updated_at, :user_notes
        )
        """,
        row,
    )
    conn.execute(
        """
        INSERT INTO tools_fts(
            tool_id, virtual_tool_name, display_name, description, category,
            evaluation_reasons, tags, capabilities, user_notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["tool_id"],
            row["virtual_tool_name"],
            row["display_name"],
            row["description"],
            row["category"],
            "",
            " ".join(tags),
            " ".join(caps),
            "",
        ),
    )
    conn.commit()
    conn.close()
    return public_id


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _mock_github_skill_api(_selection, api_path: str):
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
            "content": _b64("---\nname: upstream-demo\n---\n# Demo\nUse upstream notes.\n"),
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
            "content": _b64("print('planner github script')\n"),
        },
    }
    return responses[api_path]


def _write_valid_guide(tool_store: Path, tool_name: str) -> None:
    tool_dir = tool_store / tool_name
    tool_dir.mkdir(parents=True, exist_ok=True)
    tool_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {tool_name}\n"
        "description: Existing guide.\n"
        "---\n"
        f"Use this skill when `{tool_name}` is already available for registry-backed planning.\n",
        encoding="utf-8",
    )


def test_selected_candidate_limit_matches_requested_tool_count() -> None:
    assert planner_registry._selected_candidate_limit(None) == 3
    assert planner_registry._selected_candidate_limit(0) == 0
    assert planner_registry._selected_candidate_limit(12) == 12


def test_fts_query_splits_hyphenated_skill_names() -> None:
    assert planner_registry._fts_query("metaapp-builder") == "metaapp* AND builder*"


def test_registry_phase_materializes_missing_ready_tool_and_writes_feedback(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    artifacts = tmp_path / "task" / "planner_artifacts"

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Materialize tool {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=artifacts,
    )

    tool_names = {item["name"] for item in result.tool_pool["tools"]}
    assert public_id in tool_names
    assert result.feedback.selected_ids == [public_id]
    assert [item.tool_name for item in result.feedback.materialized_tools] == [public_id]
    assert result.feedback.failed_tools == []

    artifact = json.loads((artifacts / "registry_materialization.json").read_text(encoding="utf-8"))
    assert artifact["materialized_tools"][0]["tool_name"] == public_id
    assert artifact["final_available_tool_names"] == [public_id]
    assert "origin" not in json.dumps(artifact).lower()
    assert list((tmp_path / "task").rglob("*.sqlite")) == []

    prompt = opencode_backend.build_generation_prompt(
        scenario="Prepare a PDF report summary.",
        tool_pool=result.tool_pool,
        runtime_manifest=result.runtime_manifest,
        task_id="registry-success",
        name="Registry Success",
        domain_hints=["document"],
        tool_count=1,
        scenario_model={"domain": "document", "publication_sinks": ["workspace"]},
        registry_feedback=result.feedback.as_dict(),
    )
    assert "Registry SQLite Search and Materialization Feedback" in prompt
    assert "searched the local SQLite registry" in prompt
    assert "materialized selected GitHub-hosted skill folders or embedded OpenART tool files" in prompt
    assert public_id in prompt
    assert "registry.search" not in prompt
    assert "tool_registry.sqlite" not in prompt


def test_registry_phase_materializes_more_than_eight_requested_tools(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_ids = [
        _add_registry_tool(
            tool_store,
            name=f"PDF Report Extractor {index:02d}",
            description="Extract text from PDF reports for planner registry coverage.",
            capabilities=["document_processing", "pdf", "report"],
        )
        for index in range(12)
    ]

    result = planner_registry.run_registry_materialization_phase(
        scenario="Prepare a PDF report extraction workflow with registry tools",
        tool_store_root=tool_store,
        tool_count=12,
        artifact_dir=tmp_path / "artifacts",
    )

    tool_names = {item["name"] for item in result.tool_pool["tools"]}
    assert len(result.feedback.selected_ids) == 12
    assert set(result.feedback.selected_ids) == set(public_ids)
    assert len(result.feedback.materialized_tools) + len(result.feedback.reused_tools) == 12
    assert set(public_ids).issubset(tool_names)
    assert set(public_ids).issubset(set(result.feedback.final_available_tool_names))


def test_registry_phase_reuses_valid_materialized_tool_without_overwrite(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    planner_registry._materialize_registry_tools(_registry_path(tool_store), [public_id], tool_store)
    tool_yaml = tool_store / public_id / "tool.yaml"
    original = tool_yaml.read_text(encoding="utf-8")
    tool_yaml.write_text(original + "\n# sentinel: keep existing folder\n", encoding="utf-8")

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Materialize tool {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert [item.status for item in result.feedback.reused_tools] == ["already_available"]
    assert [item.materialization_mode for item in result.feedback.reused_tools] == ["already_available"]
    assert result.feedback.materialized_tools == []
    assert "# sentinel: keep existing folder" in tool_yaml.read_text(encoding="utf-8")


def test_registry_phase_materializes_github_script_skill_as_real_tool(monkeypatch, tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(
        tool_store,
        name="Demo Script Skill",
        description="Run a downloaded script skill.",
        include_openart_tool=False,
        source_url="https://github.com/acme/tools/tree/main/skills/demo",
        capabilities=["demo_script"],
    )
    monkeypatch.setattr(planner_registry.github_registry_install, "_github_api_json", _mock_github_skill_api)

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Use {public_id} to run demo script work",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.feedback.selected_ids == [public_id]
    assert result.feedback.failed_tools == []
    assert result.feedback.materialized_tools[0].materialization_mode == "github_script_tool"
    assert result.feedback.materialized_tools[0].source_url == "https://github.com/acme/tools/tree/main/skills/demo"

    manifest = load_tool_store_manifest(tool_store, selected_names={public_id})
    tool = manifest["tools"][0]
    assert tool["name"] == public_id
    assert tool["config"]["tool_store"]["guide_only"] is False
    assert tool["config"]["tool_store"]["source_files"] == ["scripts/openart_skill_runner.py", "scripts/run.py"]
    assert (tool_store / public_id / "references" / "original_tool.yaml").is_file()
    assert public_id in {item["name"] for item in result.tool_pool["tools"]}


def test_registry_phase_reuses_base_tool_pool_without_github_api(monkeypatch, tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(
        tool_store,
        name="Base Pool Skill",
        include_openart_tool=False,
        source_url="https://github.com/acme/tools/tree/main/skills/demo",
    )

    def fail_api(_selection, _api_path: str):
        raise AssertionError("GitHub API should not be called for already available base-pool tools")

    monkeypatch.setattr(planner_registry.github_registry_install, "_github_api_json", fail_api)
    base_tool_pool = {
        "tools": [
            {
                "name": public_id,
                "description": "Already loaded tool.",
                "capabilities": ["existing"],
            }
        ],
        "capability_groups": {"existing": [public_id]},
    }

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Use {public_id}",
        tool_store_root=tool_store,
        base_tool_pool=base_tool_pool,
        tool_count=1,
    )

    assert result.feedback.materialized_tools == []
    assert result.feedback.failed_tools == []
    assert result.feedback.reused_tools[0].status == "already_available"
    assert result.feedback.reused_tools[0].materialization_mode == "already_available"
    assert public_id in {item["name"] for item in result.tool_pool["tools"]}


def test_registry_phase_reuses_valid_store_tool_without_github_api(monkeypatch, tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(
        tool_store,
        name="Existing GitHub Skill",
        include_openart_tool=False,
        source_url="https://github.com/acme/tools/tree/main/skills/demo",
    )
    _write_valid_guide(tool_store, public_id)

    def fail_api(_selection, _api_path: str):
        raise AssertionError("GitHub API should not be called for valid existing tool-store folders")

    monkeypatch.setattr(planner_registry.github_registry_install, "_github_api_json", fail_api)

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Use {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
    )

    assert result.feedback.materialized_tools == []
    assert result.feedback.failed_tools == []
    assert result.feedback.reused_tools[0].status == "already_available"
    assert result.feedback.reused_tools[0].source_url == "https://github.com/acme/tools/tree/main/skills/demo"
    assert not list(tool_store.glob(f"{public_id}.invalid.*"))


def test_registry_phase_resolves_raw_record_skill_url(monkeypatch, tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(
        tool_store,
        name="Raw Skill URL",
        include_openart_tool=False,
        raw_extra={"record": {"skill_url": "https://github.com/acme/tools/tree/main/skills/demo"}},
    )
    monkeypatch.setattr(planner_registry.github_registry_install, "_github_api_json", _mock_github_skill_api)

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Use {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
    )

    assert result.feedback.failed_tools == []
    assert result.feedback.materialized_tools[0].source_url == "https://github.com/acme/tools/tree/main/skills/demo"
    assert result.feedback.materialized_tools[0].materialization_mode == "github_script_tool"


def test_registry_phase_github_failure_does_not_create_synthetic_guide(monkeypatch, tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(
        tool_store,
        name="Broken GitHub Skill",
        include_openart_tool=False,
        source_url="https://github.com/acme/tools/tree/main/skills/demo",
    )

    def fail_api(_selection, api_path: str):
        raise RuntimeError(f"simulated GitHub failure for {api_path}")

    monkeypatch.setattr(planner_registry.github_registry_install, "_github_api_json", fail_api)

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Use {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.feedback.materialized_tools == []
    assert result.feedback.failed_tools[0].tool_name == public_id
    assert result.feedback.failed_tools[0].status == "failed"
    assert "simulated GitHub failure" in result.feedback.failed_tools[0].reason
    assert not (tool_store / public_id).exists()
    assert public_id not in {item["name"] for item in result.tool_pool["tools"]}


def test_materialize_registry_tools_writes_declared_payload_files(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    result = planner_registry._materialize_registry_tools(_registry_path(tool_store), [public_id], tool_store)

    tool_dir = tool_store / public_id
    assert tool_dir.is_dir()
    assert (tool_dir / "SKILLS.md").is_file()
    assert (tool_dir / "tool.yaml").is_file()
    assert (tool_dir / "scripts" / "materialize_stub.py").is_file()
    assert not (tool_dir / "scripts" / "registry_run_tool.py").is_file()
    assert result["tools"] == [str(tool_dir)]


def test_materialize_registry_tools_rejects_path_traversal_payload(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    index = _registry_path(tool_store)

    conn = sqlite3.connect(index)
    row = conn.execute(
        "SELECT raw FROM tools WHERE virtual_tool_name = ?",
        (public_id,),
    ).fetchone()
    raw = json.loads(row[0])
    raw["openart_tool"]["files"][0]["path"] = "../bad.py"
    raw["openart_tool"]["tool_yaml"]["source_files"] = ["../bad.py"]
    conn.execute(
        "UPDATE tools SET raw = ? WHERE virtual_tool_name = ?",
        (json.dumps(raw), public_id),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="safe relative path"):
        planner_registry._materialize_registry_tools(index, [public_id], tool_store)


def test_registry_phase_rematerializes_invalid_existing_tool_and_backups_invalid_folder(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    planner_registry._materialize_registry_tools(_registry_path(tool_store), [public_id], tool_store)

    tool_dir = tool_store / public_id
    tool_dir.joinpath("tool.yaml").write_text("name: corrupted\n", encoding="utf-8")

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Materialize tool {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
    )

    assert [item.status for item in result.feedback.materialized_tools] == ["rematerialized"]
    assert (tool_dir / "tool.yaml").is_file()
    assert list(tool_store.glob(f"{public_id}.invalid.*")), "invalid folder backup was not created"


def test_registry_phase_records_materialization_failure_and_excludes_tool(monkeypatch, tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)

    def fail_materialize(root: Path, record: dict[str, object], *, allow_replace: bool = False) -> str:
        raise RuntimeError("simulated materialization failure")

    monkeypatch.setattr(planner_registry, "_write_materialized_tool", fail_materialize)

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Materialize tool {public_id}",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.feedback.selected_ids == [public_id]
    assert result.feedback.materialized_tools == []
    assert result.feedback.failed_tools[0].tool_name == public_id
    assert "simulated materialization failure" in result.feedback.failed_tools[0].reason
    assert public_id not in {item["name"] for item in result.tool_pool["tools"]}
    assert public_id not in result.feedback.final_available_tool_names

    feedback_text = planner_registry.format_registry_materialization_feedback(result.feedback)
    assert "Registry expansion failed for all selected candidates" in feedback_text
    assert '"final_available_tool_names": []' in feedback_text


def test_registry_phase_materializes_metadata_only_rows_as_guide_only_tools(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    metadata_only_id = _add_registry_tool(tool_store, include_openart_tool=False)

    result = planner_registry.run_registry_materialization_phase(
        scenario=f"Use tool {metadata_only_id}",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.feedback.selected_ids == [metadata_only_id]
    assert [item.tool_name for item in result.feedback.materialized_tools] == [metadata_only_id]
    assert result.feedback.failed_tools == []
    assert metadata_only_id in result.feedback.final_available_tool_names

    tool_dir = tool_store / metadata_only_id
    assert (tool_dir / "SKILL.md").is_file()
    assert not (tool_dir / "tool.yaml").exists()
    manifest = load_tool_store_manifest(tool_store, selected_names={metadata_only_id})
    assert manifest["tools"][0]["config"]["tool_store"]["guide_only"] is True
    assert manifest["tools"][0]["config"]["tool_store"]["source_files"] == []
    assert "source_files" not in manifest["tools"][0]


def test_registry_phase_treats_symlink_registry_as_unavailable(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    real_index = tmp_path / "real.sqlite"
    _registry_path(tool_store).replace(real_index)
    _registry_path(tool_store).symlink_to(real_index)

    result = planner_registry.run_registry_materialization_phase(
        scenario="Prepare a PDF report summary.",
        tool_store_root=tool_store,
        tool_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert result.feedback.registry_available is False
    assert "not a symlink" in result.feedback.registry_unavailable_reason
    assert result.feedback.selected_ids == []
    assert public_id not in result.feedback.final_available_tool_names


def test_planner_cli_exposes_no_registry_selection_flags(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "--scenario",
            "Prepare a report.",
            "--output-dir",
            "task",
            "--tool-store",
            str(tmp_path / "openart-tools"),
        ]
    )

    assert not hasattr(args, "tool_registry_index")
    assert not hasattr(args, "registry_search_query")
    assert not hasattr(args, "registry_tool_id")


def test_openart_tool_registry_inspection_helpers_are_self_contained(tmp_path: Path) -> None:
    tool_store = tmp_path / "openart-tools"
    public_id = _add_registry_tool(tool_store)
    index = _registry_path(tool_store)
    repo_root = Path(__file__).resolve().parents[3]

    search = subprocess.run(
        [
            sys.executable,
            str(repo_root / "openart-tools" / "registry.search" / "scripts" / "registry_search.py"),
            "--index",
            str(index),
            "--query",
            "pdf extract",
            "--limit",
            "5",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert public_id in search.stdout

    show = subprocess.run(
        [
            sys.executable,
            str(repo_root / "openart-tools" / "registry.show" / "scripts" / "registry_show.py"),
            "--index",
            str(index),
            "--id",
            public_id,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(show.stdout)["id"] == public_id

    run_tool = subprocess.run(
        [
            sys.executable,
            str(repo_root / "openart-tools" / "registry.run_tool" / "scripts" / "registry_run_tool.py"),
            "--index",
            str(index),
            "--id",
            public_id,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(run_tool.stdout)["id"] == public_id


def test_demo_tool_scripts_execute_with_fixtures(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]

    left_csv = tmp_path / "left.csv"
    right_csv = tmp_path / "right.csv"
    join_output = tmp_path / "joined.csv"
    left_csv.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
    right_csv.write_text("id,team\n1,Ops\n2,Eng\n", encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "openart-tools" / "tool.spreadsheet_joiner.demo001" / "scripts" / "spreadsheet_joiner.py"),
            str(left_csv),
            str(right_csv),
            "id",
            str(join_output),
        ],
        check=True,
    )
    assert join_output.read_text(encoding="utf-8") == "id,name,team\n1,Alice,Ops\n2,Bob,Eng\n"

    thread_txt = tmp_path / "thread.txt"
    summary_md = tmp_path / "summary.md"
    thread_txt.write_text(
        "Action: finalize budget\nDecision: use one-pass parser\nWhat is the rollout date?\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "openart-tools" / "tool.email_thread_summarizer.demo002" / "scripts" / "email_thread_summarizer.py"),
            str(thread_txt),
            str(summary_md),
        ],
        check=True,
    )
    summary_text = summary_md.read_text(encoding="utf-8")
    assert "- finalize budget" in summary_text
    assert "- use one-pass parser" in summary_text

    availability_csv = tmp_path / "availability.csv"
    output_json = tmp_path / "shared.json"
    availability_csv.write_text(
        "participant,slot,available\n"
        "Alice,09:00,true\n"
        "Alice,10:00,1\n"
        "Bob,09:00,yes\n"
        "Bob,10:00,false\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            sys.executable,
            str(repo_root / "openart-tools" / "tool.calendar_slot_planner.demo003" / "scripts" / "calendar_slot_planner.py"),
            str(availability_csv),
            str(output_json),
        ],
        check=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["shared_slots"] == [{"slot": "09:00"}]
