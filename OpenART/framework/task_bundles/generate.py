from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import stat
import sys
from typing import Any

import yaml

from framework.task_bundles.compose import build_compose, build_env, network_name, write_compose, write_env
from framework.task_bundles.evaluator import parse_public_roots, write_public_roots
from framework.task_bundles.services import (
    DEFAULT_CATALOG_PATH,
    ServiceCatalog,
    extract_required_services,
    load_service_catalog,
)


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


def _copy_file_mode(source: str, target: str) -> str:
    """Copy file contents and mode without xattr/timestamp probing.

    ``shutil.copy2`` calls ``listxattr``/``utime`` for every file, which is
    disproportionately slow on FUSE-backed workspace mounts. The bundles only
    need contents and permission bits.
    """

    with open(source, "rb") as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
    shutil.copymode(source, target)
    return str(target)


def _ignore_caches(directory: str, names: list[str]) -> set[str]:
    """Skip Python bytecode caches when copying catalogs and task trees."""

    return {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}


def _copy_task(task_dir: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        task_dir,
        target,
        dirs_exist_ok=True,
        copy_function=_copy_file_mode,
        ignore=_ignore_caches,
    )
    # copytree preserves source modes; only ensure the task root stays writable.
    try:
        target.chmod(target.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
    except OSError:
        pass


def _copy_service_assets(
    catalog: ServiceCatalog,
    required_services: tuple[str, ...],
    destination: Path,
) -> list[str]:
    copied: list[str] = []
    assets_root = catalog.assets_root
    for asset in sorted(set(catalog.assets_for(required_services))):
        source = assets_root / asset
        if not source.exists():
            raise FileNotFoundError(f"service asset not found: {source}")
        target = destination / "service_assets" / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(
                source,
                target,
                dirs_exist_ok=True,
                copy_function=_copy_file_mode,
                ignore=_ignore_caches,
            )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_file_mode(str(source), str(target))
        copied.append(asset)
    return copied


def _hook_entrypoint(target: Path) -> str:
    for name in ("run.py", "run.sh"):
        if (target / name).is_file():
            return name
    raise FileNotFoundError(
        f"hook directory must contain run.py or run.sh: {target}"
    )


def _copy_hooks(
    catalog: ServiceCatalog,
    required_services: tuple[str, ...],
    docker_dir: Path,
    task_copy: Path,
) -> dict[str, Any]:
    """Copy catalog hook scripts into the generated bundle.

    Hook types are generic; the framework never knows which concrete service
    supplies them.
    """

    assets_root = catalog.assets_root
    common_source = assets_root / "_shared" / "hook_common.py"
    destinations = {
        "bootstrap": docker_dir / "hooks",
        "seed": docker_dir / "seed" / "hooks",
        "export": task_copy / "finalize" / "hooks",
        "attacker": docker_dir / "attacker" / "hooks",
    }
    bootstrap_lines: list[str] = []
    attacker_lines: list[str] = []
    seed_hooks: dict[str, str] = {}
    export_hooks: dict[str, str] = {}
    used: dict[str, list[str]] = {}

    for hook_type, per_service in catalog.hooks_for(required_services).items():
        root = destinations[hook_type]
        for service, asset_path in per_service.items():
            source = assets_root / asset_path
            if not source.exists():
                raise FileNotFoundError(f"service hook not found: {source}")
            target = root / service
            if target.exists():
                shutil.rmtree(target)
            if source.is_dir():
                shutil.copytree(
                source,
                target,
                dirs_exist_ok=True,
                copy_function=_copy_file_mode,
                ignore=_ignore_caches,
            )
            else:
                target.mkdir(parents=True, exist_ok=True)
                name = "run.py" if source.suffix == ".py" else "run.sh" if source.suffix == ".sh" else source.name
                _copy_file_mode(str(source), str(target / name))
            entrypoint = _hook_entrypoint(target)
            if common_source.is_file():
                _copy_file_mode(str(common_source), str(target / "hook_common.py"))
            used.setdefault(hook_type, []).append(service)
            if hook_type == "bootstrap":
                relative = target.relative_to(docker_dir.parent).as_posix()
                bootstrap_lines.append(f"{service}|{relative}")
            elif hook_type == "seed":
                seed_hooks[service] = f"/seed/hooks/{service}/{entrypoint}"
            elif hook_type == "export":
                export_hooks[service] = f"/task/finalize/hooks/{service}/{entrypoint}"
            elif hook_type == "attacker":
                attacker_lines.append(f"{service}|/attacker_config/hooks/{service}/{entrypoint}")

    return {
        "bootstrap": "\n".join(bootstrap_lines),
        "attacker": "\n".join(attacker_lines),
        "seed": seed_hooks,
        "export": export_hooks,
        "services": {key: sorted(value) for key, value in used.items()},
    }


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
    service_catalog: str | Path = DEFAULT_CATALOG_PATH,
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

    catalog = load_service_catalog(service_catalog)
    resolved_task_id = str(task_id or task_root.name).strip()
    required = extract_required_services(task_root, catalog=catalog)
    roots = parse_public_roots(task_root)
    env = build_env(resolved_task_id, required, network_mode=network_mode, catalog=catalog)
    compose = build_compose(resolved_task_id, required, network_mode=network_mode, catalog=catalog)

    output.mkdir(parents=True, exist_ok=True)
    task_copy = output / "task"
    _copy_task(task_root, task_copy)

    docker_dir = output / "docker"
    _write(docker_dir / "task.env", "\n".join(f"{key}={value}" for key, value in env.items()) + "\n")
    _write(docker_dir / "ports.env", _ports_env(openart))
    write_compose(docker_dir / "docker-compose.yml", compose)
    copied_assets = _copy_service_assets(catalog, required.services, docker_dir)
    hook_data = _copy_hooks(catalog, required.services, docker_dir, task_copy)

    services_json = json.dumps(list(required.services))
    health_env_json = json.dumps(catalog.health_env_for(required.services))
    _write(
        docker_dir / "seed" / "seed_services.py",
        _render(
            "seed_services.py.tmpl",
            {
                "SERVICES_JSON": services_json,
                "HEALTH_ENV_JSON": health_env_json,
                "SEED_HOOKS_JSON": json.dumps(hook_data["seed"]),
            },
        ),
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
                "EXPORT_HOOKS_JSON": json.dumps(hook_data["export"]),
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
        _render("attacker_run.sh.tmpl", {"ATTACKER_HOOKS": hook_data["attacker"]}),
        executable=True,
    )
    instruction_dir = task_copy / "attacker"
    _write(
        instruction_dir / "instruction.md",
        _render("attacker_instruction.md.tmpl", {"NETWORK_NAME": network_name(resolved_task_id)}),
    )

    resolved_target_config = str(Path(target_config).resolve()) if target_config else ""
    common = {
        "TASK_ID": resolved_task_id,
        "NETWORK_NAME": network_name(resolved_task_id),
        "NETWORK_MODE": network_mode,
        "OPENART_ROOT": str(openart),
        "TOOL_STORE": str(Path(tool_store).resolve()),
        "TARGET_CONFIG": resolved_target_config,
        "SERVICE_CATALOG": str(catalog.path),
        "BOOTSTRAP_HOOKS": hook_data["bootstrap"],
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
        "target_config": resolved_target_config,
        "tool_store": str(Path(tool_store).resolve()),
        "service_catalog": str(catalog.path),
        "service_assets": copied_assets,
        "hooks": hook_data["services"],
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
    parser.add_argument(
        "--service-catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="Service catalog YAML (defaults to services/catalog/services.yaml)",
    )
    parser.add_argument("--target-config", required=True, help="Explicit target config YAML")
    parser.add_argument("--network-mode", choices=["bridge", "host"], default="bridge")
    parser.add_argument("--force", action="store_true", help="Replace an existing output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without writing files")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    catalog = load_service_catalog(args.service_catalog)
    if args.dry_run:
        required = extract_required_services(args.task, catalog=catalog)
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
                    "service_catalog": str(catalog.path),
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
        service_catalog=args.service_catalog,
        force=args.force,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())