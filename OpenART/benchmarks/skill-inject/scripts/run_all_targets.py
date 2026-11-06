#!/usr/bin/env python3
"""Run Skill-Inject tasks against every target harness config.

This is a model-backed compatibility script. It enumerates
configs/target-configs/target*.yaml, builds the matching runner image when
missing, runs the clean task, and optionally runs the injection task for
targets that declare one of the pack's skill surfaces.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

BENCH = Path(__file__).resolve().parents[1]
OPENART = BENCH.parents[1]
CONFIG_DIR = OPENART / "configs" / "target-configs"
RUN_TASK = BENCH / "scripts" / "run_task.sh"
BUILD_CONTEXT = Path("/tmp/openart-empty-build-context")
PACK_SKILL_PATHS = {
    ".agents/skills/<skill-name>/SKILL.md",
    ".claude/skills/<skill-name>/SKILL.md",
}
DEFAULT_CLEAN_TASK = "benchmarks/skill-inject/tasks/clean-1-pptx"
DEFAULT_INJECT_TASK = "benchmarks/skill-inject/tasks/obvious-1-05-pptx"
EXCLUDED = {"target.local-smoke.yaml"}


def target_name(path: Path) -> str:
    name = "opencode" if path.name == "target.yaml" else path.name[len("target.") : -len(".yaml")]
    return name.replace("-", "_")


def load_harnesses() -> dict[str, dict[str, Any]]:
    harnesses: dict[str, dict[str, Any]] = {}
    for path in sorted(CONFIG_DIR.glob("target*.yaml")):
        if path.name in EXCLUDED:
            continue
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        target = config.get("target") if isinstance(config, dict) else None
        if not isinstance(target, dict):
            continue
        skills = {
            str(surface.get("path_template"))
            for surface in target.get("attack_surfaces", [])
            if isinstance(surface, dict) and surface.get("kind") == "skill"
        }
        harnesses[target_name(path)] = {
            "name": target_name(path),
            "config_path": path,
            "image": str(target.get("runner_image") or ""),
            "skills": skills,
            "pack_skills": sorted(skills & PACK_SKILL_PATHS),
            "can_inject": bool(skills & PACK_SKILL_PATHS),
        }
    return harnesses


def dockerfile_for(image: str) -> Path:
    tag = image.rsplit("/", 1)[-1].split(":", 1)[0]
    path = OPENART / "images" / f"Dockerfile.{tag}"
    if not path.is_file():
        raise SystemExit(f"no Dockerfile for runner image {image}: {path}")
    return path


def image_exists(image: str) -> bool:
    return subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def build_image(image: str) -> bool:
    BUILD_CONTEXT.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "build",
        "--network",
        "host",
        "-t",
        image,
        "-f",
        str(dockerfile_for(image)),
    ]
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            command.extend(["--build-arg", f"{key}={proxy}"])
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
        if no_proxy:
            for key in ("NO_PROXY", "no_proxy"):
                command.extend(["--build-arg", f"{key}={no_proxy}"])
    for key in ("GOOSE_RELEASE_BASE_URL", "NPM_REGISTRY", "PIP_INDEX_URL"):
        value = os.environ.get(key)
        if value:
            command.extend(["--build-arg", f"{key}={value}"])
    command.append(str(BUILD_CONTEXT))
    print(f"building {image}", flush=True)
    return subprocess.run(command, check=False).returncode == 0


def find_result(root: Path) -> Path | None:
    candidates = sorted(root.rglob("result.json"), key=lambda path: path.stat().st_mtime)
    return candidates[-1] if candidates else None


def cleanup_run_containers(output_dir: Path) -> None:
    """Remove target/task containers left behind by a timed-out run."""
    for run_dir in output_dir.iterdir() if output_dir.is_dir() else []:
        if not run_dir.is_dir():
            continue
        for role in ("target", "task"):
            container_ids = subprocess.run(
                ["docker", "ps", "-aq", "--filter", f"name=openart-{role}-{run_dir.name}"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.split()
            if container_ids:
                subprocess.run(
                    ["docker", "rm", "-f", *container_ids],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )


def run_task(
    harness: dict[str, Any],
    mode: str,
    task: str,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OUT_DIR"] = str(output_dir)
    env.setdefault("OPENART_TARGET_DOCKER_NETWORK", "host")
    command = [
        "timeout",
        str(timeout_seconds),
        "bash",
        str(RUN_TASK),
        "--target-config",
        str(harness["config_path"]),
        "--task",
        task,
    ]
    print(f"\n== {harness['name']} / {mode}", flush=True)
    completed = subprocess.run(command, cwd=OPENART, env=env, check=False)
    cleanup_run_containers(output_dir)

    result_path = find_result(output_dir)
    if result_path is None:
        return {
            "target": harness["name"],
            "mode": mode,
            "task": task,
            "decision": "runtime_error",
            "score": 0.0,
            "rationale": f"runner exited {completed.returncode} without result.json",
            "output_dir": str(output_dir),
        }
    data = json.loads(result_path.read_text(encoding="utf-8"))
    return {
        "target": harness["name"],
        "mode": mode,
        "task": task,
        "decision": data.get("decision", ""),
        "score": data.get("score"),
        "rationale": data.get("rationale", ""),
        "output_dir": str(result_path.parent),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", nargs="+", default=None)
    parser.add_argument("--list-targets", action="store_true")
    parser.add_argument("--list-missing", action="store_true")
    parser.add_argument("--modes", choices=("clean", "both"), default="clean")
    parser.add_argument("--clean-task", default=DEFAULT_CLEAN_TASK)
    parser.add_argument("--inject-task", default=DEFAULT_INJECT_TASK)
    parser.add_argument("--output-dir", default=str(OPENART / "runs" / "skill-inject-all-targets"))
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--prune-images", action="store_true")
    args = parser.parse_args()

    harnesses = load_harnesses()
    if args.list_targets:
        for name, harness in harnesses.items():
            print(
                f"{name:16} {harness['image']:32} "
                f"can_inject={harness['can_inject']}"
            )
        return 0

    if args.list_missing:
        missing = [
            harness["image"]
            for harness in harnesses.values()
            if not image_exists(harness["image"])
        ]
        print("\n".join(missing))
        return 0

    selected = args.targets or list(harnesses)
    unknown = [name for name in selected if name not in harnesses]
    if unknown:
        print(f"unknown targets: {', '.join(unknown)}", file=sys.stderr)
        return 2

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []

    for name in selected:
        harness = harnesses[name]
        if not image_exists(harness["image"]):
            if args.no_build:
                summary.append(
                    {
                        "target": name,
                        "mode": "build",
                        "decision": "missing_image",
                        "score": 0.0,
                        "rationale": f"image not present: {harness['image']}",
                        "output_dir": "",
                    }
                )
                continue
            if not build_image(harness["image"]):
                summary.append(
                    {
                        "target": name,
                        "mode": "build",
                        "decision": "build_error",
                        "score": 0.0,
                        "rationale": f"docker build failed: {harness['image']}",
                        "output_dir": "",
                    }
                )
                continue

        modes = [("clean", args.clean_task)]
        if args.modes == "both" and harness["can_inject"]:
            modes.append(("inject", args.inject_task))
        for mode, task in modes:
            row = run_task(
                harness,
                mode,
                task,
                output_root / name / mode,
                args.timeout_seconds,
            )
            summary.append(row)
            print(
                f"{name:16} {mode:7} {row['decision']:14} "
                f"score={row['score']} {row['rationale']}",
                flush=True,
            )

        if args.prune_images and harness["image"] != "openart/opencode:latest":
            subprocess.run(
                ["docker", "rmi", harness["image"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    summary_path = output_root / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"\nsummary: {summary_path}")

    failures = [
        row
        for row in summary
        if row["decision"] in {"runtime_error", "build_error", "missing_image"}
    ]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())