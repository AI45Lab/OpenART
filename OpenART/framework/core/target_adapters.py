"""Target-agent model delivery helpers.

Target configs declare how model credentials are delivered to the target-native
CLI. The runtime resolves the binding, target-native environment variable names,
and optional config templates without relying on a Python adapter registry.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

import yaml

try:  # pragma: no cover - Python 3.11+ path
    import tomllib  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - Python 3.8-3.10 fallback
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except Exception:  # pragma: no cover
        tomllib = None  # type: ignore[assignment]


SUPPORTED_DELIVERY_TYPES = {"env_only", "config_template", "hybrid"}
SUPPORTED_TEMPLATE_FORMATS = {"json", "yaml", "toml", "text"}
MODEL_CONFIG_MOUNT_PATH_TEMPLATE = "/workspace/.openart_model_integration_{role}.{ext}"
_PLACEHOLDER_PATTERN = re.compile(r"\$\{([^}]+)\}")
_SECRET_KEY_MARKERS = ("api_key", "apikey", "auth_token", "token", "secret", "password")
_ENV_NAME_MODEL_FIELDS = {
    "api_key": "api_key",
    "base_url": "base_url",
    "model": "model",
}
_SURFACE_FAMILY_ALIASES = {
    "claude": "claude_code",
    "claude_code": "claude_code",
    "gemini_cli": "gemini",
    "open_code": "opencode",
    "opencode": "opencode",
    "codex_cli": "codex",
}


@dataclass(frozen=True)
class RenderedConfig:
    host_path: str
    mount_path: str
    destination: str
    format: str


@dataclass(frozen=True)
class ModelIntegrationResult:
    provider_family: str
    delivery_type: str
    env_names: dict[str, str]
    env: dict[str, str]
    config: RenderedConfig | None
    model_binding: dict[str, str]
    resolved_artifact_path: str


def canonical_surface_family(value: Any) -> str:
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _SURFACE_FAMILY_ALIASES.get(key, key)


def surface_family_from_target_config(target_config: Mapping[str, Any]) -> str:
    surface_family = canonical_surface_family(target_config.get("surface_family"))
    if surface_family:
        return surface_family
    return canonical_surface_family(target_config.get("framework"))


def _model_lookup_key(key: str) -> str:
    if key in {"name", "model"}:
        return "model"
    return key


def _base_url_root(value: str) -> str:
    text = str(value or "").strip().rstrip("/")
    return text[:-3].rstrip("/") if text.endswith("/v1") else text


def _base_url_v1(value: str) -> str:
    root = _base_url_root(value)
    return f"{root}/v1" if root else ""


def _normalize_model_binding_urls(binding: dict[str, str]) -> None:
    base_url = str(binding.get("base_url") or "").strip()
    if not base_url:
        return

    binding["base_url_root"] = _base_url_root(base_url)
    binding["base_url_v1"] = _base_url_v1(base_url)
    provider_family = str(binding.get("provider_family") or "").strip().lower()

    if provider_family in {"anthropic", "anthropic_compatible", "claude", "claude_code"}:
        binding["base_url"] = binding["base_url_root"]
    elif provider_family in {"openai", "openai_compatible"}:
        binding["base_url"] = binding["base_url_v1"]


def _resolve_template_string(
    text: str,
    *,
    model: Mapping[str, str],
    env: Mapping[str, str],
    env_names: Mapping[str, str],
    source_label: str,
) -> str:
    missing: list[str] = []

    def replacement(match: re.Match[str]) -> str:
        token = match.group(1).strip()
        if token.startswith("model."):
            field = _model_lookup_key(token[len("model."):].strip())
            value = model.get(field, "")
            if value:
                return str(value)
            missing.append(token)
            return match.group(0)
        if token.startswith("env_name."):
            env_name_key = token[len("env_name."):].strip()
            value = env_names.get(env_name_key, "")
            if value:
                return str(value)
            missing.append(token)
            return match.group(0)
        if token.startswith("env."):
            env_name = token[len("env."):].strip()
            value = env.get(env_name, "")
            if value:
                return str(value)
            missing.append(token)
            return match.group(0)
        value = env.get(token, "")
        if value:
            return str(value)
        missing.append(token)
        return match.group(0)

    rendered = _PLACEHOLDER_PATTERN.sub(replacement, text)
    if missing:
        unique = ", ".join(sorted(set(missing)))
        raise ValueError(f"unresolved placeholder(s) in {source_label}: {unique}")
    return rendered


def resolve_template_value(
    value: Any,
    *,
    model: Mapping[str, str],
    env: Mapping[str, str] | None = None,
    env_names: Mapping[str, str] | None = None,
    source_label: str = "model_integration",
) -> Any:
    env = env or os.environ
    env_names = env_names or {}
    if isinstance(value, str):
        return _resolve_template_string(
            value,
            model=model,
            env=env,
            env_names=env_names,
            source_label=source_label,
        )
    if isinstance(value, list):
        return [
            resolve_template_value(
                item,
                model=model,
                env=env,
                env_names=env_names,
                source_label=source_label,
            )
            for item in value
        ]
    if isinstance(value, dict):
        resolved: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            resolved_key = _resolve_template_string(
                key_text,
                model=model,
                env=env,
                env_names=env_names,
                source_label=source_label,
            )
            resolved[resolved_key] = resolve_template_value(
                item,
                model=model,
                env=env,
                env_names=env_names,
                source_label=source_label,
            )
        return resolved
    return value


def resolve_model_binding(
    integration_cfg: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    required_fields: tuple[str, ...] = (),
    require_binding: bool = False,
) -> dict[str, str]:
    env = env or os.environ
    raw_binding = integration_cfg.get("binding") if isinstance(integration_cfg, Mapping) else None
    binding: dict[str, str] = {}

    if isinstance(raw_binding, Mapping):
        for key, value in raw_binding.items():
            key_text = str(key or "").strip()
            if not key_text:
                continue
            rendered = resolve_template_value(
                str(value or ""),
                model={},
                env=env,
                source_label=f"model_integration.binding.{key_text}",
            )
            normalized_key = "model" if key_text == "name" else key_text
            binding[normalized_key] = str(rendered)
    elif require_binding:
        raise ValueError("model_integration.binding is required for model delivery")
    else:
        fallback = {
            "provider_family": env.get("TARGET_PROVIDER_FAMILY", ""),
            "api_key": env.get("TARGET_API_KEY", ""),
            "base_url": env.get("TARGET_BASE_URL", ""),
            "model": env.get("TARGET_MODEL", ""),
        }
        binding.update({key: value for key, value in fallback.items() if value})

    if not binding.get("provider_family") and env.get("TARGET_PROVIDER_FAMILY"):
        binding["provider_family"] = str(env.get("TARGET_PROVIDER_FAMILY") or "")
    if "name" not in binding and binding.get("model"):
        binding["name"] = binding["model"]
    if "model" not in binding and binding.get("name"):
        binding["model"] = binding["name"]
    _normalize_model_binding_urls(binding)

    missing = [field for field in required_fields if not binding.get(_model_lookup_key(field))]
    if missing:
        raise ValueError("model_integration.binding missing required field(s): " + ", ".join(missing))

    return binding


def _merge_env_maps(*items: Any) -> dict[str, str]:
    merged: dict[str, str] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        for key, value in item.items():
            env_name = str(key or "").strip()
            if env_name:
                merged[env_name] = str(value or "")
    return merged


def normalize_env_names(raw_env_names: Any) -> dict[str, str]:
    if not isinstance(raw_env_names, Mapping):
        return {}
    env_names: dict[str, str] = {}
    for key, value in raw_env_names.items():
        name = str(key or "").strip()
        env_var = str(value or "").strip()
        if name and env_var:
            env_names[name] = env_var
    return env_names


def normalize_delivery(integration_cfg: Mapping[str, Any]) -> dict[str, Any]:
    raw_delivery = integration_cfg.get("delivery") if isinstance(integration_cfg, Mapping) else None
    delivery = dict(raw_delivery) if isinstance(raw_delivery, Mapping) else {}

    legacy_config_json = integration_cfg.get("config_json")
    if isinstance(legacy_config_json, Mapping) and "config_template" not in delivery:
        template = dict(legacy_config_json)
        template.setdefault("format", "json")
        delivery["config_template"] = template

    env_names = normalize_env_names(delivery.get("env_names"))
    explicit_env = _merge_env_maps(integration_cfg.get("env"), delivery.get("env"))
    delivery["env_names"] = env_names
    delivery["env"] = explicit_env

    if "type" not in delivery:
        has_template = isinstance(delivery.get("config_template"), Mapping)
        has_env = bool(env_names or explicit_env)
        if has_template and has_env:
            delivery["type"] = "hybrid"
        elif has_template:
            delivery["type"] = "config_template"
        else:
            delivery["type"] = "env_only"

    delivery_type = str(delivery.get("type") or "").strip().lower()
    if delivery_type == "generated_config":
        raise ValueError(
            "model_integration.delivery.type generated_config is no longer supported; "
            "use delivery.config_template with a static template file"
        )
    if delivery_type not in SUPPORTED_DELIVERY_TYPES:
        raise ValueError(
            f"unsupported model_integration delivery type: {delivery_type}. "
            f"Supported types: {', '.join(sorted(SUPPORTED_DELIVERY_TYPES))}"
        )
    delivery["type"] = delivery_type
    return delivery


def resolve_model_integration_source_path(
    source_spec: str,
    *,
    repo_root: Path,
    target_config_path: str | None = None,
) -> Path:
    if source_spec.startswith("target:"):
        if not target_config_path:
            raise ValueError("model_integration config template source with target: requires target_config_path")
        base = Path(target_config_path).resolve().parent
        path = base / source_spec[len("target:"):]
    elif source_spec.startswith("repo:"):
        path = repo_root / source_spec[len("repo:"):]
    elif source_spec.startswith("abs:"):
        path = Path(source_spec[len("abs:"):])
    else:
        raise ValueError("model_integration config template source must start with target:, repo:, or abs:")
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"model_integration config template source does not exist: {resolved}")
    return resolved


def expand_model_integration_destination(
    destination_spec: str,
    runtime_env: Mapping[str, str],
    symbolic_roots: Mapping[str, Any],
) -> str:
    text = str(destination_spec or "").strip()
    if not text:
        raise ValueError("model_integration config template destination is required")
    if text.startswith("/"):
        return text
    root, _, remainder = text.partition("/")
    if root not in symbolic_roots:
        raise ValueError(
            "model_integration config template destination must start with one of "
            + ", ".join(f"{name}/" for name in sorted(symbolic_roots))
        )
    resolver = symbolic_roots[root]
    base = str(resolver(runtime_env) if callable(resolver) else resolver or "").strip()
    if not base:
        raise ValueError(f"model_integration config template destination root is unavailable: {root}")
    return f"{base.rstrip('/')}/{remainder}" if remainder else base


def _format_extension(format_name: str) -> str:
    return {"yaml": "yaml", "json": "json", "toml": "toml", "text": "txt"}[format_name]


def _validate_rendered_content(content: str, format_name: str, source_label: str) -> None:
    if format_name == "json":
        json.loads(content)
        return
    if format_name == "yaml":
        yaml.safe_load(content)
        return
    if format_name == "toml" and tomllib is not None:
        tomllib.loads(content)
        return
    if format_name == "text":
        return


def render_config_template(
    template_spec: Mapping[str, Any],
    *,
    model: Mapping[str, str],
    env: Mapping[str, str] | None = None,
    env_names: Mapping[str, str] | None = None,
    repo_root: Path,
    target_config_path: str | None,
) -> tuple[str, str, str]:
    env = env or os.environ
    env_names = env_names or {}
    format_name = str(template_spec.get("format") or "json").strip().lower()
    if format_name not in SUPPORTED_TEMPLATE_FORMATS:
        raise ValueError(
            f"unsupported model_integration config template format: {format_name}. "
            f"Supported formats: {', '.join(sorted(SUPPORTED_TEMPLATE_FORMATS))}"
        )

    source_path: Path | None = None
    source_spec = str(template_spec.get("source") or "").strip()
    content = template_spec.get("content")
    source_label = "model_integration.config_template"

    if source_spec:
        source_path = resolve_model_integration_source_path(
            source_spec,
            repo_root=repo_root,
            target_config_path=target_config_path,
        )
        source_label = str(source_path)
        content_text = source_path.read_text(encoding="utf-8")
    elif content is not None:
        content_text = content if isinstance(content, str) else ""
    else:
        raise ValueError("model_integration config template requires source or content")

    if isinstance(content, Mapping) and not source_spec:
        resolved_obj = resolve_template_value(
            content,
            model=model,
            env=env,
            env_names=env_names,
            source_label=source_label,
        )
        if format_name == "json":
            rendered = json.dumps(resolved_obj, ensure_ascii=True, indent=2) + "\n"
        elif format_name == "yaml":
            rendered = yaml.safe_dump(resolved_obj, sort_keys=False)
        else:
            raise ValueError(f"inline structured content is not supported for format: {format_name}")
    elif format_name == "json":
        parsed = json.loads(content_text)
        rendered_obj = resolve_template_value(
            parsed,
            model=model,
            env=env,
            env_names=env_names,
            source_label=source_label,
        )
        rendered = json.dumps(rendered_obj, ensure_ascii=True, indent=2) + "\n"
    elif format_name == "yaml":
        parsed = yaml.safe_load(content_text) or {}
        rendered_obj = resolve_template_value(
            parsed,
            model=model,
            env=env,
            env_names=env_names,
            source_label=source_label,
        )
        rendered = yaml.safe_dump(rendered_obj, sort_keys=False)
    else:
        rendered = resolve_template_value(
            content_text,
            model=model,
            env=env,
            env_names=env_names,
            source_label=source_label,
        )
        if not rendered.endswith("\n"):
            rendered += "\n"

    _validate_rendered_content(rendered, format_name, source_label)
    name = source_path.name if source_path is not None else f"generated.{_format_extension(format_name)}"
    return rendered, name, format_name


def redact_model_binding(model_binding: Mapping[str, str]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in model_binding.items():
        key_text = str(key)
        if any(marker in key_text.lower() for marker in _SECRET_KEY_MARKERS):
            redacted[key_text] = "<redacted>" if value else ""
        else:
            redacted[key_text] = str(value or "")
    return redacted


def _required_fields_for_env_names(env_names: Mapping[str, str]) -> tuple[str, ...]:
    fields: list[str] = []
    for name in env_names:
        field = _ENV_NAME_MODEL_FIELDS.get(name)
        if field and field not in fields:
            fields.append(field)
    return tuple(fields)


def _resolve_env_names_payload(env_names: Mapping[str, str], model_binding: Mapping[str, str]) -> dict[str, str]:
    env_payload: dict[str, str] = {}
    missing: list[str] = []
    for name, env_var in env_names.items():
        field = _ENV_NAME_MODEL_FIELDS.get(name)
        if field is None:
            continue
        value = str(model_binding.get(field) or "").strip()
        if not value:
            missing.append(f"model.{field}")
            continue
        env_payload[str(env_var)] = value
    if missing:
        raise ValueError("model_integration.binding missing required field(s): " + ", ".join(sorted(set(missing))))
    return env_payload


def write_resolved_model_artifact(
    path: Path,
    *,
    provider_family: str,
    delivery_type: str,
    env_names: Mapping[str, str],
    model_binding: Mapping[str, str],
    env_payload: Mapping[str, str],
    config: RenderedConfig | None,
) -> str:
    payload: dict[str, Any] = {
        "provider_family": provider_family,
        "delivery_type": delivery_type,
        "binding": redact_model_binding(model_binding),
        "env_names": dict(env_names),
        "env_keys": sorted(env_payload),
        "config": None,
    }
    if config is not None:
        payload["config"] = {
            "host_path": config.host_path,
            "mount_path": config.mount_path,
            "destination": config.destination,
            "format": config.format,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return str(path)


def stage_model_integration(
    integration_cfg: Mapping[str, Any],
    *,
    role: str,
    runtime_env: Mapping[str, str],
    output_dir: str | Path,
    target_config_path: str | None,
    repo_root: Path,
    symbolic_roots: Mapping[str, Any],
) -> ModelIntegrationResult | None:
    if not isinstance(integration_cfg, Mapping) or not integration_cfg:
        return None

    delivery = normalize_delivery(integration_cfg)
    delivery_type = str(delivery["type"])
    env_names = normalize_env_names(delivery.get("env_names"))
    resolution_env = {str(key): str(value) for key, value in os.environ.items()}
    resolution_env.update({str(key): str(value) for key, value in runtime_env.items()})

    model_binding = resolve_model_binding(
        integration_cfg,
        env=resolution_env,
        required_fields=_required_fields_for_env_names(env_names),
        require_binding=True,
    )

    env_payload = _resolve_env_names_payload(env_names, model_binding)
    rendered_env_raw = delivery.get("env") if isinstance(delivery.get("env"), Mapping) else {}
    rendered_env = resolve_template_value(
        dict(rendered_env_raw),
        model=model_binding,
        env=resolution_env,
        env_names=env_names,
        source_label="model_integration.delivery.env",
    )
    env_payload.update({str(key): str(value or "") for key, value in rendered_env.items() if str(key).strip()})

    rendered_config: RenderedConfig | None = None
    if delivery_type in {"config_template", "hybrid"}:
        template_spec = delivery.get("config_template")
        if not isinstance(template_spec, Mapping):
            raise ValueError(f"model_integration delivery type {delivery_type} requires a config template")
        rendered, source_name, format_name = render_config_template(
            template_spec,
            model=model_binding,
            env=resolution_env,
            env_names=env_names,
            repo_root=repo_root,
            target_config_path=target_config_path,
        )
        destination = expand_model_integration_destination(
            str(template_spec.get("destination") or ""),
            runtime_env,
            symbolic_roots,
        )
        staged_dir = Path(output_dir) / "model_integration" / role
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged_path = staged_dir / source_name
        staged_path.write_text(rendered, encoding="utf-8")
        rendered_config = RenderedConfig(
            host_path=str(staged_path),
            mount_path=MODEL_CONFIG_MOUNT_PATH_TEMPLATE.format(role=role, ext=_format_extension(format_name)),
            destination=destination,
            format=format_name,
        )

    artifact_path = Path(output_dir) / "model_integration" / role / "model_integration_resolved.json"
    provider_family = str(model_binding.get("provider_family") or "").strip()
    resolved_artifact_path = write_resolved_model_artifact(
        artifact_path,
        provider_family=provider_family,
        delivery_type=delivery_type,
        env_names=env_names,
        model_binding=model_binding,
        env_payload=env_payload,
        config=rendered_config,
    )

    return ModelIntegrationResult(
        provider_family=provider_family,
        delivery_type=delivery_type,
        env_names=env_names,
        env=env_payload,
        config=rendered_config,
        model_binding=model_binding,
        resolved_artifact_path=resolved_artifact_path,
    )
