"""Shared contract for benchmark materializers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Protocol


MATERIALIZED_TASK_SCHEMA_VERSION = 1
REQUIRED_MATERIALIZED_PATHS = ("task.md", "task_spec.json")


class MaterializeError(RuntimeError):
    """Raised when a benchmark task cannot be materialized safely."""


@dataclass(frozen=True)
class MaterializeResult:
    task_dir: Path
    task_spec: dict[str, Any]


class Materializer(Protocol):
    name: str

    def materialize(
        self,
        task_id: str,
        output_dir: Path,
        *,
        options: Mapping[str, Any] | None = None,
    ) -> MaterializeResult:
        ...


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def validate_materialized_task(root: str | Path) -> list[str]:
    """Return contract violations for a materialized task directory."""

    bundle_root = Path(root)
    errors: list[str] = []
    if not bundle_root.is_dir():
        return [f"materialized task directory does not exist: {bundle_root}"]

    for relative in REQUIRED_MATERIALIZED_PATHS:
        if not (bundle_root / relative).is_file():
            errors.append(f"required materialized file is missing: {relative}")

    spec_path = bundle_root / "task_spec.json"
    if not spec_path.is_file():
        return errors

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return errors + [f"task_spec.json is not valid JSON: {exc}"]

    if not isinstance(spec, Mapping):
        return errors + ["task_spec.json must contain an object"]

    if int(spec.get("schema_version", 0) or 0) != MATERIALIZED_TASK_SCHEMA_VERSION:
        errors.append(
            "task_spec.json schema_version must be "
            f"{MATERIALIZED_TASK_SCHEMA_VERSION}"
        )
    if not str(spec.get("task_id", "") or "").strip():
        errors.append("task_spec.json task_id is required")

    utility = spec.get("utility")
    if isinstance(utility, Mapping):
        kind = str(utility.get("kind", "") or "").strip()
        if kind not in {"native", "external", "none"}:
            errors.append("task_spec.json utility.kind must be native, external, or none")
        path_value = str(utility.get("path", "") or "").strip()
        if kind in {"native", "external"}:
            if not path_value:
                errors.append("task_spec.json utility.path is required for a measured utility channel")
            elif not (bundle_root / path_value).is_file():
                errors.append(f"utility evaluator is missing: {path_value}")
    else:
        errors.append("task_spec.json utility object is required")

    surface = spec.get("safety_surface")
    if not isinstance(surface, Mapping):
        errors.append("task_spec.json safety_surface object is required")

    return errors