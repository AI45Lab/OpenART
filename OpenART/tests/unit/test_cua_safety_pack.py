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