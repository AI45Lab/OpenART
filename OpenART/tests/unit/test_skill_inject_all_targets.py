from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml

PACK = Path(__file__).resolve().parents[2] / "benchmarks" / "skill-inject"
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

EXPECTED_INJECTION_CAPABLE = {
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
    spec = importlib.util.spec_from_file_location("skill_inject_all_targets", ALL_TARGETS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_target_configs_are_covered_and_have_dockerfiles() -> None:
    runner = _load_all_targets_runner()
    harnesses = runner.load_harnesses()
    assert set(harnesses) == EXPECTED_HARNESSES
    for name, harness in harnesses.items():
        assert harness["image"], name
        assert runner.dockerfile_for(harness["image"]).is_file(), name


def test_all_targets_injection_capability_matches_pack_layout() -> None:
    runner = _load_all_targets_runner()
    harnesses = runner.load_harnesses()
    capable = {name for name, harness in harnesses.items() if harness["can_inject"]}
    assert capable == EXPECTED_INJECTION_CAPABLE


def test_all_targets_runner_lists_every_harness() -> None:
    result = subprocess.run(
        [sys.executable, str(ALL_TARGETS), "--list-targets"],
        check=True,
        capture_output=True,
        text=True,
    )
    listed = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
    assert listed == EXPECTED_HARNESSES


def test_all_targets_runner_forwards_mirror_build_args() -> None:
    source = ALL_TARGETS.read_text(encoding="utf-8")
    for key in ("GOOSE_RELEASE_BASE_URL", "NPM_REGISTRY", "PIP_INDEX_URL"):
        assert f'"{key}"' in source


def test_codex_template_uses_gateway_compatible_reasoning() -> None:
    template = (
        PACK.parents[1] / "configs" / "target-model-json" / "codex.openai-compatible.toml"
    ).read_text(encoding="utf-8")
    assert 'model_reasoning_effort = "low"' in template
    assert "model_supports_reasoning_summaries" not in template
    assert "model_reasoning_summary" not in template


def test_claude_and_codex_use_gateway_compat_hook() -> None:
    expected_harness = {"claude-code": "claude_code", "codex": "codex"}
    for config_name, harness in expected_harness.items():
        config = yaml.safe_load(
            (PACK.parents[1] / "configs" / "target-configs" / f"target.{config_name}.yaml").read_text(
                encoding="utf-8"
            )
        )
        target = config["target"]
        hook = target["pre_run_hook"]
        assert hook == "repo:configs/target-hooks/llm-gateway-compat.py"
        assert target["model_integration"]["delivery"]["env"]["OPENART_LLM_GATEWAY_COMPAT"] == harness
        assert (PACK.parents[1] / hook[len("repo:") :]).is_file()


def test_hermes_image_uses_python_314_via_uv() -> None:
    dockerfile = (PACK.parents[1] / "images" / "Dockerfile.hermes").read_text(encoding="utf-8")
    assert "uv python install 3.14" in dockerfile
    assert "uv sync --frozen" in dockerfile
    assert "ARG HERMES_AGENT_REF=main" in dockerfile


def test_openclaw_image_pins_node_tarball() -> None:
    dockerfile = (PACK.parents[1] / "images" / "Dockerfile.openclaw").read_text(encoding="utf-8")
    assert "ARG NODE_VERSION=24" in dockerfile
    assert "node-v${NODE_VERSION}-linux-x64.tar.xz" in dockerfile
    assert "ARG NPM_REGISTRY" in dockerfile
    assert "npm install -g n" not in dockerfile


def test_nanobot_config_path_is_outside_workspace() -> None:
    config = yaml.safe_load(
        (PACK.parents[1] / "configs" / "target-configs" / "target.nanobot.yaml").read_text(
            encoding="utf-8"
        )
    )
    launch = config["target"]["launch_cmd"]
    assert "--config /tmp/openart/runners/target/home/.nanobot/config.json" in launch
    delivery = config["target"]["model_integration"]["delivery"]
    assert delivery["config_template"]["destination"] == "HOME/.nanobot/config.json"


def test_reasonix_uses_generated_config_and_trust_hook() -> None:
    config = yaml.safe_load(
        (PACK.parents[1] / "configs" / "target-configs" / "target.reasonix.yaml").read_text(
            encoding="utf-8"
        )
    )
    target = config["target"]
    launch = target["launch_cmd"]
    hook = target["pre_run_hook"]
    assert "--no-config" not in launch
    assert "--no-proxy" not in launch
    assert "--print" in launch
    assert "--yolo" in launch
    assert hook == "repo:configs/target-hooks/reasonix-bind-credentials.sh"
    delivery = target["model_integration"]["delivery"]
    assert delivery["type"] == "hybrid"
    assert delivery["config_template"]["source"] == (
        "repo:configs/target-model-json/reasonix.openai-compatible.toml"
    )
    assert delivery["config_template"]["destination"] == "HOME/.reasonix/config.toml"
    hook_text = (PACK.parents[1] / hook[len("repo:") :]).read_text(encoding="utf-8")
    assert "DEEPSEEK_API_KEY" in hook_text
    assert "reasonix trust --dir /workspace --yes" in hook_text
    template = (
        PACK.parents[1]
        / "configs"
        / "target-model-json"
        / "reasonix.openai-compatible.toml"
    ).read_text(encoding="utf-8")
    assert 'kind = "openai"' in template
    assert 'bash = "off"' in template


def test_deepseek_launch_binds_credentials_via_hook() -> None:
    config = yaml.safe_load(
        (PACK.parents[1] / "configs" / "target-configs" / "target.deepseek-tui.yaml").read_text(
            encoding="utf-8"
        )
    )
    launch = config["target"]["launch_cmd"]
    hook = config["target"]["pre_run_hook"]
    assert "--api-key" not in launch
    assert "--base-url" not in launch
    env_names = config["target"]["model_integration"]["delivery"]["env_names"]
    assert env_names["base_url"] != "DEEPSEEK_BASE_URL"
    assert hook == "repo:configs/target-hooks/codewhale-bind-credentials.sh"
    hook_text = (PACK.parents[1] / hook[len("repo:") :]).read_text(encoding="utf-8")
    assert "config_path = home / \".codewhale\" / \"config.toml\"" in hook_text
    assert 'api_key = os.environ.get("DEEPSEEK_API_KEY", "")' in hook_text
    assert "codewhale config set" not in hook_text
    template = (
        PACK.parents[1]
        / "configs"
        / "target-model-json"
        / "deepseek-tui.openai-compatible.toml"
    ).read_text(encoding="utf-8")
    assert "api_key_env" not in template
    assert "base_url_env" not in template


def test_goose_image_uses_direct_release_tarball() -> None:
    dockerfile = (PACK.parents[1] / "images" / "Dockerfile.goose").read_text(encoding="utf-8")
    assert "GOOSE_RELEASE_BASE_URL" in dockerfile
    assert "goose-x86_64-unknown-linux-gnu.tar.bz2" in dockerfile
    assert "/root/.local/bin/goose" in dockerfile
    assert "download_cli.sh" not in dockerfile


def test_nanobot_image_uses_configurable_pip_index() -> None:
    dockerfile = (PACK.parents[1] / "images" / "Dockerfile.nanobot").read_text(encoding="utf-8")
    assert "ARG PIP_INDEX_URL" in dockerfile
    assert "--index-url" in dockerfile