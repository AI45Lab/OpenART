from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
from typing import Any

import yaml

from framework.task_bundles.compose import build_compose, build_env, network_name, write_compose, write_env
from framework.task_bundles.evaluator import parse_public_roots, write_public_roots
from framework.task_bundles.services import extract_required_services


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OPENART_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOL_STORE = DEFAULT_OPENART_ROOT.parent / "openart-tools"


def _render(template_name: str, values: dict[str, Any]) -> str:
    text = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", str(value))
    return text


def _write(path: Path, content: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_task(task_dir: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(task_dir, target, dirs_exist_ok=True)
    for root, dirs, _files in os.walk(target):
        for name in dirs:
            path = Path(root) / name
            try:
                path.chmod(path.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
            except OSError:
                pass


def _ports_env(openart_root: Path) -> str:
    source = openart_root / "services" / "configs" / "ports.env"
    if source.is_file():
        return source.read_text(encoding="utf-8")
    return "SERVICE_BIND_HOST=127.0.0.1\n"


def _attacker_config(task_id: str, *, network_mode: str) -> dict[str, Any]:
    network = "host" if network_mode == "host" else network_name(task_id)
    return {
        "attacker": {
            "name": "live-service-attacker",
            "phase": "before_target",
            "enabled": True,
            "instruction": "attacker/instruction.md",
            "image": "openart/task-base:latest",
            "cmd": "/bin/bash",
            "args": ["/attacker_config/run.sh"],
            "network": network,
            "vector_permissions": ["workspace_files", "service_state"],
            "feedback_loop": False,
            "timeout_seconds": 1800,
        }
    }


def generate_bundle(
    task_dir: str | Path,
    output_dir: str | Path,
    *,
    task_id: str = "",
    openart_root: str | Path = DEFAULT_OPENART_ROOT,
    tool_store: str | Path = DEFAULT_TOOL_STORE,
    target_config: str = "",
    network_mode: str = "bridge",
    force: bool = False,
) -> dict[str, Any]:
    task_root = Path(task_dir).resolve()
    output = Path(output_dir).resolve()
    openart = Path(openart_root).resolve()
    if not (task_root / "task.md").is_file():
        raise FileNotFoundError(f"task.md not found in {task_root}")
    if network_mode not in {"bridge", "host"}:
        raise ValueError("network_mode must be 'bridge' or 'host'")
    if output == task_root or task_root in output.parents:
        raise ValueError("output directory must not be the task directory or a parent of it")
    if output.exists() and any(output.iterdir()) and not force:
        raise FileExistsError(f"output directory is not empty: {output} (use --force)")

    resolved_task_id = str(task_id or task_root.name).strip()
    required = extract_required_services(task_root)
    roots = parse_public_roots(task_root)
    env = build_env(resolved_task_id, required, network_mode=network_mode)
    compose = build_compose(resolved_task_id, required, network_mode=network_mode)

    output.mkdir(parents=True, exist_ok=True)
    task_copy = output / "task"
    _copy_task(task_root, task_copy)

    docker_dir = output / "docker"
    _write(docker_dir / "task.env", "\n".join(f"{key}={value}" for key, value in env.items()) + "\n")
    _write(docker_dir / "ports.env", _ports_env(openart))
    write_compose(docker_dir / "docker-compose.yml", compose)

    services_json = json.dumps(list(required.services))
    _write(
        docker_dir / "seed" / "seed_services.py",
        _render("seed_services.py.tmpl", {"SERVICES_JSON": services_json}),
        executable=True,
    )

    finalize_dir = task_copy / "finalize"
    _write(
        finalize_dir / "export_services.py",
        _render(
            "export_services.py.tmpl",
            {
                "SERVICES_JSON": services_json,
                "PUBLIC_ROOTS_JSON": json.dumps(list(roots)),
            },
        ),
        executable=True,
    )
    write_public_roots(task_copy, roots)

    attacker_dir = docker_dir / "attacker"
    _write(
        attacker_dir / "config.yaml",
        yaml.safe_dump(_attacker_config(resolved_task_id, network_mode=network_mode), sort_keys=False),
    )
    _write(
        attacker_dir / "run.sh",
        _render("attacker_run.sh.tmpl", {}),
        executable=True,
    )
    instruction_dir = task_copy / "attacker"
    _write(
        instruction_dir / "instruction.md",
        _render("attacker_instruction.md.tmpl", {"NETWORK_NAME": network_name(resolved_task_id)}),
    )

    common = {
        "TASK_ID": resolved_task_id,
        "NETWORK_NAME": network_name(resolved_task_id),
        "NETWORK_MODE": network_mode,
        "HAS_GITLAB": "1" if "gitlab" in required.services else "0",
        "OPENART_ROOT": str(openart),
        "TOOL_STORE": str(Path(tool_store).resolve()),
        "TARGET_CONFIG": target_config,
    }
    _write(output / "up.sh", _render("up.sh.tmpl", common), executable=True)
    _write(output / "run.sh", _render("run.sh.tmpl", common), executable=True)
    _write(output / "down.sh", _render("down.sh.tmpl", common), executable=True)
    _write(
        output / "README.md",
        _render(
            "README.md.tmpl",
            {**common, "SERVICES_LIST": "\n".join(f"- `{name}`" for name in required.services) or "- none"},
        ),
    )

    return {
        "task_id": resolved_task_id,
        "output_dir": str(output),
        "services": list(required.services),
        "compose_services": list(required.compose_services),
        "unknown_services": list(required.unknown),
        "public_roots": list(roots),
        "network_mode": network_mode,
        "network_name": network_name(resolved_task_id),
        "target_config": target_config,
        "tool_store": str(Path(tool_store).resolve()),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a self-contained Docker Compose bundle for one OpenART task.",
    )
    parser.add_argument("--task", required=True, help="Extracted task directory (contains task.md)")
    parser.add_argument("--out", required=True, help="Output bundle directory")
    parser.add_argument("--task-id", default="", help="Task id (defaults to the task directory name)")
    parser.add_argument("--openart-root", default=str(DEFAULT_OPENART_ROOT), help="OpenART checkout root")
    parser.add_argument("--tool-store", default=str(DEFAULT_TOOL_STORE), help="openart-tools store path")
    parser.add_argument("--target-config", required=True, help="Explicit target config YAML")
    parser.add_argument("--network-mode", choices=["bridge", "host"], default="bridge")
    parser.add_argument("--force", action="store_true", help="Replace an existing output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.dry_run:
        required = extract_required_services(args.task)
        roots = parse_public_roots(args.task)
        print(
            json.dumps(
                {
                    "task_id": args.task_id or Path(args.task).resolve().name,
                    "services": list(required.services),
                    "compose_services": list(required.compose_services),
                    "unknown_services": list(required.unknown),
                    "public_roots": list(roots),
                    "network_mode": args.network_mode,
                },
                indent=2,
            )
        )
        return 0
    result = generate_bundle(
        args.task,
        args.out,
        task_id=args.task_id,
        openart_root=args.openart_root,
        tool_store=args.tool_store,
        target_config=args.target_config,
        network_mode=args.network_mode,
        force=args.force,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())