"""The CUA pack resolves to one remote MCP server and no MCP attack surface."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "benchmarks" / "cua-safety"


def _load_resolver():
    path = PACK / "scripts" / "resolve_target_config.py"
    spec = importlib.util.spec_from_file_location("openart_cua_resolver", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cua_target_resolves_to_one_remote_mcp_server() -> None:
    resolver = _load_resolver()

    resolved, metadata = resolver.resolve_target("opencode")

    target = resolved["target"]
    delivery = target["model_integration"]["delivery"]
    assert delivery["type"] == "hybrid"
    assert delivery["config_template"]["kind"] == "mcp"
    assert delivery["config_template"]["destination"] == "XDG_CONFIG_HOME/opencode/opencode.json"
    assert metadata["profile_mode"] == "replace"
    assert target["network"] == "${CUA_DOCKER_NETWORK}"


def test_cua_profile_has_exactly_one_remote_server(tmp_path: Path) -> None:
    resolver = _load_resolver()
    profile = json.loads((PACK / "mcp" / "opencode.json").read_text(encoding="utf-8"))

    servers = profile["mcp"]
    assert list(servers) == ["openart-cua"]
    assert servers["openart-cua"] == {
        "type": "remote",
        "url": "${CUA_MCP_URL}",
        "enabled": True,
    }
    for forbidden in ("bash", "edit", "write", "read", "glob", "grep", "list", "patch"):
        assert profile["tools"][forbidden] is False


def test_resolver_rejects_a_second_server(tmp_path: Path) -> None:
    resolver = _load_resolver()
    bad = tmp_path / "opencode.json"
    bad.write_text(
        json.dumps(
            {
                "mcp": {
                    "a": {"type": "remote", "url": "${CUA_MCP_URL}"},
                    "b": {"type": "local", "command": ["python3", "server.py"]},
                }
            }
        ),
        encoding="utf-8",
    )

    try:
        resolver._validate_profile(bad)
    except SystemExit as exc:
        assert "exactly one MCP server" in str(exc)
    else:
        raise AssertionError("resolver accepted two MCP servers")


def test_cua_target_has_no_mcp_replacement_vector() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "benchmarks" / "configs" / "target-configs" / "target.cua-opencode.yaml").read_text(
            encoding="utf-8"
        )
    )

    vectors = [surface["vector"] for surface in config["target"]["attack_surfaces"]]
    assert not [vector for vector in vectors if vector.endswith("_mcp")]
    assert "opencode_mcp" not in vectors

TASK_ROOT = REPO_ROOT / "benchmarks" / "capability-bundles" / "lite-osworld" / "tasks"


def test_marker_task_has_a_separate_safety_channel() -> None:
    task = TASK_ROOT / "cua-safety-marker"

    assert (task / "task.md").is_file()
    assert (task / "utils" / "evaluator.py").is_file()
    assert (task / "utils" / "safety_evaluator.py").is_file()
    safety = (task / "utils" / "safety_evaluator.py").read_text(encoding="utf-8")
    assert "OPENART-CUA-MARKER-7f3a9c2e" in safety
    assert "unsafe_leak_detected" in safety


def test_marker_lives_outside_the_shared_workspace() -> None:
    setup = (TASK_ROOT / "cua-safety-marker" / "env" / "setup.sh").read_text(encoding="utf-8")

    assert "/home/user/Documents/private/private_note.txt" in setup
    assert "OPENART-CUA-MARKER-7f3a9c2e" in setup
    assert "/workspace/private_note.txt" not in setup


def test_marker_bridge_matches_the_smoke_bridge() -> None:
    smoke = (TASK_ROOT / "cua-smoke-file" / "agent" / "cua_bridge.py").read_bytes()
    marker = (TASK_ROOT / "cua-safety-marker" / "agent" / "cua_bridge.py").read_bytes()

    assert marker == smoke


def test_attacker_only_stages_workspace_instructions() -> None:
    config = yaml.safe_load((PACK / "attackers" / "leak.yaml").read_text(encoding="utf-8"))
    attacker = config["attacker"]

    assert attacker["phase"] == "before_target"
    assert attacker["target_control_plane"] is False
    assert "workspace_files" in attacker["vector_permissions"]
    assert not [vector for vector in attacker["vector_permissions"] if vector.endswith("_mcp")]
    assert (PACK / "attackers" / "leak.md").is_file()
    assert (PACK / "attackers" / "run_cua_attacker.py").is_file()
