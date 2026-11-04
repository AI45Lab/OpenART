from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from framework.core.control_plane import build_provider_from_attack_surfaces


TARGET_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "target-configs"

EXPECTED_MCP_VECTORS = {
    "target.yaml": "opencode_mcp",
    "target.claude-code.yaml": "claude_mcp",
    "target.codex.yaml": "codex_mcp",
    "target.deepseek-tui.yaml": "codewhale_mcp",
    "target.copilot-cli.yaml": "copilot_mcp",
    "target.gemini.yaml": "gemini_mcp",
    "target.qwen-code.yaml": "qwen_mcp",
    "target.continue-cli.yaml": "continue_mcp",
    "target.goose.yaml": "goose_mcp",
    "target.hermes.yaml": "hermes_mcp",
    "target.kilo.yaml": "kilo_mcp",
    "target.nanobot.yaml": "nanobot_mcp",
    "target.pi.yaml": "pi_mcp",
    "target.reasonix.yaml": "reasonix_mcp",
    "target.oh-my-pi.yaml": "omp_mcp",
    "target.openclaw.yaml": "openclaw_mcp",
}


def _load_target(filename: str) -> dict:
    path = TARGET_CONFIG_DIR / filename
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), filename
    target = data.get("target")
    assert isinstance(target, dict), filename
    return target


@pytest.mark.parametrize(("filename", "vector"), sorted(EXPECTED_MCP_VECTORS.items()))
def test_target_exposes_mcp_surface(filename: str, vector: str) -> None:
    target = _load_target(filename)
    surfaces = target.get("attack_surfaces") or []
    by_vector = {
        str(surface.get("vector")): surface
        for surface in surfaces
        if isinstance(surface, dict)
    }
    assert vector in by_vector, f"{filename} is missing {vector}"

    surface = by_vector[vector]
    assert surface.get("kind") == "configuration"
    assert str(surface.get("path_template", "")).strip()
    assert surface.get("injection_mode") in {"replace", "append", "merge"}

    provider = build_provider_from_attack_surfaces(
        str(target.get("surface_family") or target.get("framework") or filename),
        surfaces,
    )
    assert vector in provider.attacker_vector_patterns


def test_aider_has_no_native_mcp_surface() -> None:
    target = _load_target("target.aider.yaml")
    surfaces = target.get("attack_surfaces") or []
    vectors = {
        str(surface.get("vector"))
        for surface in surfaces
        if isinstance(surface, dict)
    }
    assert not any(vector.endswith("_mcp") for vector in vectors)