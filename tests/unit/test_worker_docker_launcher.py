from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_all_tasks_with_worker_docker.py"
SPEC = importlib.util.spec_from_file_location("run_all_tasks_with_worker_docker", SCRIPT_PATH)
assert SPEC is not None
worker_docker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = worker_docker
assert SPEC.loader is not None
SPEC.loader.exec_module(worker_docker)


def _make_task(root: Path, name: str) -> Path:
    task = root / name
    task.mkdir(parents=True)
    (task / "task.md").write_text("# task\n", encoding="utf-8")
    return task


def test_shard_tasks_uses_stable_round_robin(tmp_path: Path) -> None:
    tasks = [_make_task(tmp_path, name) for name in ["a", "b", "c", "d", "e"]]

    shards = worker_docker.shard_tasks(tasks, 2)

    assert [[task.name for task in shard] for shard in shards] == [["a", "c", "e"], ["b", "d"]]


def test_worker_command_bootstraps_worker_local_docker(tmp_path: Path) -> None:
    tasks_root = tmp_path / "tasks"
    task = _make_task(tasks_root, "alpha")
    output_dir = tmp_path / "out"
    args = worker_docker.parse_args(
        [
            "--tasks-root",
            str(tasks_root),
            "--output-dir",
            str(output_dir),
            "--batch-id",
            "batch",
            "--worker-count",
            "1",
            "--worker-parallelism",
            "2",
            "--rlaunch-script",
            "/opt/rlaunch_cpu_forever.sh",
            "--privileged",
            "--image",
            "registry.example/ml-base:22.04",
            "--",
            "--target-config",
            "configs/target.yaml",
        ]
    )

    plans = worker_docker.build_worker_plans(
        repo_root=tmp_path,
        tasks_root=tasks_root,
        output_dir=output_dir,
        batch_id="batch",
        tasks=[task],
        args=args,
    )

    assert len(plans) == 1
    command = plans[0].command
    shell_script = command[-1]
    assert command[:7] == [
        "/opt/rlaunch_cpu_forever.sh",
        "--memory",
        "32G",
        "--cpu",
        "4",
        "--image",
        "registry.example/ml-base:22.04",
    ]
    assert "--privileged" in command
    assert command[-4:] == ["--", "bash", "-lc", shell_script]
    assert "unset DOCKER_HOST DOCKER_TLS_VERIFY DOCKER_CERT_PATH" in shell_script
    assert "dockerd --storage-driver=fuse-overlayfs --data-root=/docker-data" in shell_script
    assert "scripts/run_all_tasks_with_timing.py" in shell_script
    assert "--batch-id batch-shard-001" in shell_script
    assert "--parallelism 2" in shell_script
    assert "--task alpha" in shell_script
    assert "--target-config configs/target.yaml" in shell_script


def test_dry_run_prints_json_plan_without_submission(tmp_path: Path, capsys) -> None:
    tasks_root = tmp_path / "tasks"
    _make_task(tasks_root, "alpha")
    _make_task(tasks_root, "beta")

    code = worker_docker.main(
        [
            "--tasks-root",
            str(tasks_root),
            "--output-dir",
            str(tmp_path / "out"),
            "--batch-id",
            "batch",
            "--worker-count",
            "2",
            "--rlaunch-script",
            "/opt/rlaunch_cpu_forever.sh",
            "--dry-run",
            "--",
            "--continue-on-error",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["batch_id"] == "batch"
    assert payload["worker_count_scheduled"] == 2
    assert payload["batch_runner_args"] == ["--continue-on-error"]
    assert [worker["tasks"] for worker in payload["workers"]] == [["alpha"], ["beta"]]
