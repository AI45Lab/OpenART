from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import yaml

from framework.core.target_adapters import render_config_template, stage_model_integration
from scripts import validate_target_adapter as validator


def _symbolic_roots():
    return {
        "HOME": lambda env: env.get("HOME", ""),
        "XDG_CONFIG_HOME": lambda env: env.get("XDG_CONFIG_HOME", ""),
        "XDG_DATA_HOME": lambda env: env.get("XDG_DATA_HOME", ""),
        "XDG_CACHE_HOME": lambda env: env.get("XDG_CACHE_HOME", ""),
        "WORKSPACE": lambda env: "/workspace",
        "RUNNER_STATE_DIR": lambda env: env.get("OPENART_RUNNER_STATE_DIR", ""),
    }


def _runtime_env() -> dict[str, str]:
    return {
        "HOME": "/tmp/openart/home",
        "XDG_CONFIG_HOME": "/tmp/openart/config",
        "XDG_DATA_HOME": "/tmp/openart/data",
        "XDG_CACHE_HOME": "/tmp/openart/cache",
        "OPENART_RUNNER_STATE_DIR": "/tmp/openart/state",
    }


def _target_config_file(tmp_path: Path) -> Path:
    path = tmp_path / "target.yaml"
    path.write_text("target: {}\n", encoding="utf-8")
    return path


def test_render_config_template_supports_env_name_placeholders_in_all_formats(tmp_path: Path) -> None:
    model = {"api_key": "secret-key", "base_url": "http://llm.internal/v1", "model": "glm-5", "name": "glm-5"}
    env_names = {"api_key": "OPENAI_API_KEY", "base_url": "OPENAI_BASE_URL", "model": "OPENAI_MODEL"}
    repo_root = tmp_path
    target_config_path = _target_config_file(tmp_path)
    json_template = tmp_path / "config.json"
    yaml_template = tmp_path / "config.yaml"
    toml_template = tmp_path / "config.toml"
    text_template = tmp_path / "config.txt"
    json_template.write_text(
        '{"models": {"${model.name}": {"base": "${model.base_url}", "env": "${env_name.api_key}"}}}\n',
        encoding="utf-8",
    )
    yaml_template.write_text("model: ${model.name}\nmodel_env: ${env_name.model}\n", encoding="utf-8")
    toml_template.write_text('model = "${model.name}"\nenv_key = "${env_name.api_key}"\n', encoding="utf-8")
    text_template.write_text("model=${model.name}\nkey=${env_name.api_key}\n", encoding="utf-8")

    rendered_json, _, _ = render_config_template(
        {"source": f"abs:{json_template}", "format": "json"},
        model=model,
        env_names=env_names,
        repo_root=repo_root,
        target_config_path=str(target_config_path),
    )
    rendered_yaml, _, _ = render_config_template(
        {"source": f"abs:{yaml_template}", "format": "yaml"},
        model=model,
        env_names=env_names,
        repo_root=repo_root,
        target_config_path=str(target_config_path),
    )
    rendered_toml, _, _ = render_config_template(
        {"source": f"abs:{toml_template}", "format": "toml"},
        model=model,
        env_names=env_names,
        repo_root=repo_root,
        target_config_path=str(target_config_path),
    )
    rendered_text, _, _ = render_config_template(
        {"source": f"abs:{text_template}", "format": "text"},
        model=model,
        env_names=env_names,
        repo_root=repo_root,
        target_config_path=str(target_config_path),
    )

    parsed_json = json.loads(rendered_json)
    assert parsed_json["models"]["glm-5"]["base"] == "http://llm.internal/v1"
    assert parsed_json["models"]["glm-5"]["env"] == "OPENAI_API_KEY"
    assert yaml.safe_load(rendered_yaml)["model_env"] == "OPENAI_MODEL"
    assert 'env_key = "OPENAI_API_KEY"' in rendered_toml
    assert "key=OPENAI_API_KEY" in rendered_text


def test_env_names_expand_before_explicit_env_merge(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "secret-key")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    result = stage_model_integration(
        {
            "binding": {
                "provider_family": "openai_compatible",
                "api_key": "${TARGET_API_KEY}",
                "base_url": "${TARGET_BASE_URL}",
                "model": "${TARGET_MODEL}",
            },
            "delivery": {
                "type": "env_only",
                "env_names": {
                    "api_key": "OPENAI_API_KEY",
                    "base_url": "OPENAI_BASE_URL",
                    "model": "OPENAI_MODEL",
                },
                "env": {
                    "OPENAI_MODEL": "override-model",
                    "OPENART_ENV_KEY_NAME": "${env_name.api_key}",
                },
            },
        },
        role="target",
        runtime_env=_runtime_env(),
        output_dir=tmp_path,
        target_config_path=str(_target_config_file(tmp_path)),
        repo_root=Path(__file__).resolve().parents[2],
        symbolic_roots=_symbolic_roots(),
    )

    assert result is not None
    assert result.env["OPENAI_API_KEY"] == "secret-key"
    assert result.env["OPENAI_BASE_URL"] == "http://llm.internal/v1"
    assert result.env["OPENAI_MODEL"] == "override-model"
    assert result.env["OPENART_ENV_KEY_NAME"] == "OPENAI_API_KEY"
    artifact = json.loads(Path(result.resolved_artifact_path).read_text(encoding="utf-8"))
    assert artifact["provider_family"] == "openai_compatible"
    assert artifact["env_names"]["api_key"] == "OPENAI_API_KEY"
    assert "adapter" + "_name" not in artifact


def test_builtin_target_configs_stage_model_delivery(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "secret-key")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "configs" / "target-configs"
    results = {}

    for config_path in sorted(config_dir.glob("target*.yaml")):
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        target = data.get("target") if isinstance(data, dict) else {}
        integration = target.get("model_integration") if isinstance(target, dict) else None
        if not isinstance(integration, dict):
            continue
        assert "adapter" not in integration
        surface_family = str(target.get("surface_family") or "").strip()
        assert surface_family
        result = stage_model_integration(
            integration,
            role="target",
            runtime_env=_runtime_env(),
            output_dir=tmp_path / surface_family,
            target_config_path=str(config_path),
            repo_root=repo_root,
            symbolic_roots=_symbolic_roots(),
        )
        assert result is not None
        results[surface_family] = result

    assert results["claude_code"].env["ANTHROPIC_AUTH_TOKEN"] == "secret-key"
    assert results["claude_code"].env["ANTHROPIC_BASE_URL"] == "http://llm.internal"
    assert results["cursor"].env["CURSOR_API_KEY"] == "secret-key"
    assert results["gemini"].env["GEMINI_API_KEY"] == "secret-key"
    assert results["gemini"].env["GEMINI_MODEL"] == "glm-5"

    opencode = json.loads(Path(results["opencode"].config.host_path).read_text(encoding="utf-8"))
    assert opencode["provider"]["openart"]["options"]["baseURL"] == "http://llm.internal/v1"
    assert opencode["provider"]["openart"]["options"]["apiKey"] == "{env:OPENAI_API_KEY}"
    assert "glm-5" in opencode["provider"]["openart"]["models"]

    codex_toml = Path(results["codex"].config.host_path).read_text(encoding="utf-8")
    assert 'env_key = "OPENAI_API_KEY"' in codex_toml
    assert 'wire_api = "responses"' in codex_toml

    pi = json.loads(Path(results["pi"].config.host_path).read_text(encoding="utf-8"))
    assert pi["providers"]["pjlab"]["apiKey"] == "OPENAI_API_KEY"
    assert results["pi"].env["OPENAI_API_KEY"] == "secret-key"
    assert results["pi"].env["OPENAI_BASE_URL"] == "http://llm.internal/v1"

    hermes = yaml.safe_load(Path(results["hermes"].config.host_path).read_text(encoding="utf-8"))
    assert hermes["model"]["base_url"] == "http://llm.internal/v1"

    nanobot = json.loads(Path(results["nanobot"].config.host_path).read_text(encoding="utf-8"))
    nanobot_provider = nanobot["agents"]["defaults"]["provider"]
    assert nanobot["providers"][nanobot_provider]["apiKey"] == "secret-key"

    artifact = json.loads(Path(results["nanobot"].resolved_artifact_path).read_text(encoding="utf-8"))
    assert artifact["binding"]["api_key"] == "<redacted>"
    assert "adapter" + "_name" not in artifact


def _write_validation_target(tmp_path: Path) -> Path:
    path = tmp_path / "target.yaml"
    path.write_text(
        "target:\n"
        "  framework: prompt_cli\n"
        "  surface_family: claude_code\n"
        "  model_integration:\n"
        "    binding:\n"
        "      provider_family: openai_compatible\n"
        "      api_key: ${TARGET_API_KEY}\n"
        "      base_url: ${TARGET_BASE_URL}\n"
        "      model: ${TARGET_MODEL}\n"
        "    delivery:\n"
        "      type: env_only\n"
        "      env_names:\n"
        "        api_key: ANTHROPIC_AUTH_TOKEN\n"
        "        base_url: ANTHROPIC_BASE_URL\n"
        "        model: ANTHROPIC_MODEL\n",
        encoding="utf-8",
    )
    return path


def _docs_fetcher(url: str, timeout_seconds: int) -> validator.FetchResult:
    del timeout_seconds
    modified = format_datetime(datetime.now(timezone.utc), usegmt=True)
    html = "ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_MODEL"
    return validator.FetchResult(url=url, status_code=200, text=html, headers={"Last-Modified": modified})


def _endpoint_ok(metadata, model_binding, timeout_seconds):
    del metadata, timeout_seconds
    return {"ok": True, "model": model_binding["model"]}


def test_validate_model_delivery_supported_with_official_docs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "secret-key")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    target_config_path = _write_validation_target(tmp_path)

    payload = validator.validate_adapter(
        target_config_path=target_config_path,
        require_official_docs=True,
        fetcher=_docs_fetcher,
        endpoint_probe_runner=_endpoint_ok,
    )

    assert payload["status"] == "supported"
    assert payload["surface_family"] == "claude_code"
    assert payload["docs"]["official"] is True
    assert set(payload["docs"]["matched_fields"]) == {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
    }


def test_validate_model_delivery_requires_official_docs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "secret-key")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    target_config_path = _write_validation_target(tmp_path)

    payload = validator.validate_adapter(
        target_config_path=target_config_path,
        docs_url="https://community.example.test/claude",
        require_official_docs=True,
        fetcher=_docs_fetcher,
        endpoint_probe_runner=_endpoint_ok,
    )

    assert payload["status"] == "invalid"
    assert payload["docs"]["official"] is False


def test_validate_model_delivery_marks_non_official_docs_experimental(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "secret-key")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    target_config_path = _write_validation_target(tmp_path)

    payload = validator.validate_adapter(
        target_config_path=target_config_path,
        docs_url="https://community.example.test/claude",
        require_official_docs=False,
        fetcher=_docs_fetcher,
        endpoint_probe_runner=_endpoint_ok,
    )

    assert payload["status"] == "experimental"


def test_validate_model_delivery_smoke_failure_is_integration_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TARGET_API_KEY", "secret-key")
    monkeypatch.setenv("TARGET_BASE_URL", "http://llm.internal/v1")
    monkeypatch.setenv("TARGET_MODEL", "glm-5")
    target_config_path = _write_validation_target(tmp_path)

    payload = validator.validate_adapter(
        target_config_path=target_config_path,
        require_official_docs=True,
        fetcher=_docs_fetcher,
        endpoint_probe_runner=_endpoint_ok,
        smoke_runner=lambda *args, **kwargs: {"ok": False, "error": "smoke failed"},
    )

    assert payload["status"] == "integration_error"
    assert payload["smoke"]["error"] == "smoke failed"
