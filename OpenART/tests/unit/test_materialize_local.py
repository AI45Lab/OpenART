from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.tasks.materialize import (
    LocalBundleMaterializer,
    MaterializeError,
    validate_materialized_task,
)
from framework.tasks.materialize.base import sha256_file


def _make_source(root: Path) -> Path:
    source = root / "source-task"
    (source / "utils").mkdir(parents=True)
    (source / "workspace" / "docs").mkdir(parents=True)
    (source / "task.md").write_text("Read docs and write a summary.\n", encoding="utf-8")
    (source / "utils" / "evaluator.py").write_text(
        "def evaluate(workspace_root='/workspace', **kwargs):\n"
        "    return {'decision': 'pass', 'score': 1.0}\n",
        encoding="utf-8",
    )
    (source / "workspace" / "docs" / "handbook.md").write_text("benign notes\n", encoding="utf-8")
    (source / "tool_use_graph.json").write_text(
        json.dumps({"nodes": [{"name": "shell"}, {"name": "browser"}]}),
        encoding="utf-8",
    )
    return source


def test_local_materialize_copies_task_and_records_contract(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "materialized"

    result = LocalBundleMaterializer().materialize(
        str(source),
        output,
        options={"input": str(source), "task_id": "demo-task"},
    )

    assert result.task_dir == output
    spec = json.loads((output / "task_spec.json").read_text(encoding="utf-8"))
    assert spec["task_id"] == "demo-task"
    assert spec["utility"]["kind"] == "native"
    assert spec["utility"]["path"] == "utils/evaluator.py"
    assert spec["utility"]["sha256"] == sha256_file(source / "utils" / "evaluator.py")
    assert spec["safety_surface"]["filesystem"] == ["workspace"]
    assert spec["safety_surface"]["commands"] is True
    assert spec["safety_surface"]["network"] is True
    assert (output / "workspace" / "docs" / "handbook.md").is_file()

    assert validate_materialized_task(output) == []


def test_local_materialize_requires_task_md(tmp_path: Path) -> None:
    source = tmp_path / "bad-task"
    source.mkdir()
    with pytest.raises(MaterializeError, match="task.md"):
        LocalBundleMaterializer().materialize(
            str(source),
            tmp_path / "out",
            options={"input": str(source)},
        )


def test_local_materialize_requires_overwrite(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "materialized"
    output.mkdir()
    with pytest.raises(MaterializeError, match="already exists"):
        LocalBundleMaterializer().materialize(
            str(source),
            output,
            options={"input": str(source)},
        )


def test_validator_rejects_missing_utility_evaluator(tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "materialized"
    LocalBundleMaterializer().materialize(
        str(source),
        output,
        options={"input": str(source)},
    )
    (output / "utils" / "evaluator.py").unlink()

    errors = validate_materialized_task(output)

    assert any("utility evaluator is missing" in error for error in errors)