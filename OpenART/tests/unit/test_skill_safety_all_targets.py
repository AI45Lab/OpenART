from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "benchmarks" / "skill-safety"
ALL_TARGETS = PACK / "scripts" / "run_all_targets.py"

EXPECTED_HARNESSES = {
    "aider",
    "claude_code",
    "codex",
    "continue_cli",
    "copilot_cli",
    "deepseek_tui",
    "gemini",
    "goose",
    "hermes",
    "kilo",
    "nanobot",
    "oh_my_pi",
    "openclaw",
    "opencode",
    "pi",
    "qwen_code",
    "reasonix",
}

EXPECTED_SKILL_CAPABLE = {
    "claude_code",
    "codex",
    "copilot_cli",
    "gemini",
    "goose",
    "hermes",
    "kilo",
    "oh_my_pi",
    "opencode",
    "pi",
    "qwen_code",
}


def _load_all_targets_runner():
    spec = importlib.util.spec_from_file_location("skill_safety_all_targets", ALL_TARGETS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_safety_all_target_configs_are_covered() -> None:
    runner = _load_all_targets_runner()
    harnesses = runner.load_harnesses()
    assert set(harnesses) == EXPECTED_HARNESSES
    for name, harness in harnesses.items():
        assert harness["image"], name
        assert runner.dockerfile_for(harness["image"]).is_file(), name


def test_skill_safety_all_targets_skill_capability() -> None:
    runner = _load_all_targets_runner()
    harnesses = runner.load_harnesses()
    capable = {
        name for name, harness in harnesses.items() if harness["can_read_pack_skills"]
    }
    assert capable == EXPECTED_SKILL_CAPABLE


def test_skill_safety_all_targets_lists_every_harness() -> None:
    result = subprocess.run(
        [sys.executable, str(ALL_TARGETS), "--list-targets"],
        check=True,
        capture_output=True,
        text=True,
    )
    listed = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
    assert listed == EXPECTED_HARNESSES


def test_skill_safety_all_targets_uses_pack_runner_and_mirror_args() -> None:
    source = ALL_TARGETS.read_text(encoding="utf-8")
    assert "run_task.sh" in source
    assert "load_pack_targets" in source
    assert '"--target"' in source
    assert '"--target-config"' in source
    for key in ("GOOSE_RELEASE_BASE_URL", "NPM_REGISTRY", "PIP_INDEX_URL"):
        assert f'"{key}"' in source
    assert "default=3600" in source


def test_oh_my_pi_installs_bun_from_npm() -> None:
    dockerfile = (
        PACK.parents[1] / "images" / "Dockerfile.oh-my-pi"
    ).read_text(encoding="utf-8")
    assert "npm install -g bun" in dockerfile
    assert "BUN_INSTALL=/opt/bun" in dockerfile
    assert "bun.sh/install" not in dockerfile


def test_skill_safety_all_targets_task_exists_and_is_self_contained() -> None:
    runner = _load_all_targets_runner()
    task = PACK.parents[1] / runner.DEFAULT_TASK
    assert task.is_dir(), task
    case = __import__("json").loads((task / "case.json").read_text(encoding="utf-8"))
    assert case["runtime"]["self_contained"] is True