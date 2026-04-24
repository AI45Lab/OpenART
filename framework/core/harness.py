from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


def load_harness_module(harness_path: str | None) -> ModuleType | None:
    raw_path = str(harness_path or "").strip()
    if not raw_path:
        return None
    harness_root = Path(raw_path)
    config_path = harness_root / "config.py"
    if not config_path.is_file():
        return None

    spec = importlib.util.spec_from_file_location("openart_harness_config", config_path)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_harness_settings(harness_path: str | None) -> dict[str, str]:
    _ = load_harness_module(harness_path)
    return {}


def apply_harness_settings_to_env(harness_path: str | None) -> dict[str, str]:
    _ = harness_path
    return {}


def build_harness_service_config(harness_path: str | None) -> dict[str, Any]:
    _ = harness_path
    return {}
