from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import json
import shutil
from pathlib import Path

from framework.models.specs import WorkspaceDiff


@dataclass(frozen=True, slots=True)
class ControlSurfaceSpec:
    kind: str
    path_template: str
    description: str


@dataclass(frozen=True, slots=True)
class ControlPlaneProvider:
    framework: str
    source_patterns: tuple[str, ...]
    allowed_patterns: tuple[str, ...]
    attacker_surfaces: tuple[ControlSurfaceSpec, ...]

    def collect_task_files(self, task_root: Path) -> list[tuple[Path, str]]:
        seen: set[str] = set()
        files: list[tuple[Path, str]] = []
        for pattern in self.source_patterns:
            if any(char in pattern for char in "*?["):
                candidates = sorted(task_root.glob(pattern))
            else:
                candidates = [task_root / pattern]
            for candidate in candidates:
                if not candidate.exists() or not candidate.is_file():
                    continue
                rel = candidate.relative_to(task_root).as_posix()
                if rel in seen or not self.is_allowed_relative_path(rel):
                    continue
                seen.add(rel)
                files.append((candidate, rel))
        return files

    def is_allowed_relative_path(self, relative_path: str) -> bool:
        normalized = relative_path.strip().lstrip("/")
        if not normalized:
            return False
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.allowed_patterns)


def create_control_plane_provider(framework: str) -> ControlPlaneProvider | None:
    name = (framework or "").strip().lower()
    if name == "opencode":
        return ControlPlaneProvider(
            framework="opencode",
            source_patterns=(
                "AGENTS.md",
                "CLAUDE.md",
                ".opencode/skills/**/*",
                ".opencode/commands/**/*",
                ".claude/skills/**/*",
            ),
            allowed_patterns=(
                "AGENTS.md",
                "CLAUDE.md",
                ".opencode/skills/**",
                ".opencode/commands/**",
                ".claude/skills/**",
            ),
            attacker_surfaces=(
                ControlSurfaceSpec(
                    kind="instruction",
                    path_template="AGENTS.md",
                    description="Top-level repository guidance read by OpenCode in the workspace.",
                ),
                ControlSurfaceSpec(
                    kind="instruction",
                    path_template="CLAUDE.md",
                    description="Claude-compatible instruction file also visible to OpenCode.",
                ),
                ControlSurfaceSpec(
                    kind="skill",
                    path_template=".opencode/skills/<skill-name>/SKILL.md",
                    description="Native OpenCode skill definition discovered from the workspace.",
                ),
                ControlSurfaceSpec(
                    kind="command",
                    path_template=".opencode/commands/<command-name>.md",
                    description="Native OpenCode slash-command content discovered from the workspace.",
                ),
                ControlSurfaceSpec(
                    kind="skill",
                    path_template=".claude/skills/<skill-name>/SKILL.md",
                    description="Claude-compatible skill path that OpenCode also discovers.",
                ),
            ),
        )
    if name == "claude_code":
        return ControlPlaneProvider(
            framework="claude_code",
            source_patterns=(
                "CLAUDE.md",
                ".claude/CLAUDE.md",
                ".claude/rules/**/*",
                ".claude/skills/**/*",
                ".claude/commands/**/*",
            ),
            allowed_patterns=(
                "CLAUDE.md",
                ".claude/CLAUDE.md",
                ".claude/rules/**",
                ".claude/skills/**",
                ".claude/commands/**",
            ),
            attacker_surfaces=(
                ControlSurfaceSpec(
                    kind="instruction",
                    path_template="CLAUDE.md",
                    description="Primary Claude Code repository instruction file.",
                ),
                ControlSurfaceSpec(
                    kind="instruction",
                    path_template=".claude/CLAUDE.md",
                    description="Project-local Claude Code instruction file.",
                ),
                ControlSurfaceSpec(
                    kind="rule",
                    path_template=".claude/rules/<rule-name>.md",
                    description="Claude Code rule file discovered from the workspace.",
                ),
                ControlSurfaceSpec(
                    kind="skill",
                    path_template=".claude/skills/<skill-name>/SKILL.md",
                    description="Native Claude Code skill definition discovered from the workspace.",
                ),
                ControlSurfaceSpec(
                    kind="command",
                    path_template=".claude/commands/<command-name>.md",
                    description="Native Claude Code command content discovered from the workspace.",
                ),
            ),
        )
    return None


class ControlPlaneManager:
    MANIFEST_FILE_NAME = ".openart-target-control-manifest.json"

    def __init__(self, root_dir: str, source_root: str, provider: ControlPlaneProvider | None) -> None:
        self.root_dir = Path(root_dir)
        self.source_root = Path(source_root)
        self.provider = provider

    def enabled(self) -> bool:
        return self.provider is not None

    def ensure_layout(self) -> None:
        self.base_dir().mkdir(parents=True, exist_ok=True)
        self.final_dir().mkdir(parents=True, exist_ok=True)
        self.attackers_dir().mkdir(parents=True, exist_ok=True)
        self.snapshots_dir().mkdir(parents=True, exist_ok=True)

    def base_dir(self) -> Path:
        return self.root_dir / "base"

    def final_dir(self) -> Path:
        return self.root_dir / "final"

    def attackers_dir(self) -> Path:
        return self.root_dir / "attackers"

    def snapshots_dir(self) -> Path:
        return self.root_dir / "snapshots"

    def manifest_path(self) -> Path:
        return self.base_dir() / self.MANIFEST_FILE_NAME

    def attacker_output_dir(self, attacker_name: str, phase: str, index: int = 1) -> Path:
        return self.attackers_dir() / attacker_name / f"{phase}_{index:03d}"

    def ensure_attacker_output(self, attacker_name: str, phase: str, index: int = 1) -> str:
        path = self.attacker_output_dir(attacker_name, phase, index)
        self._clear_dir_contents(path)
        return str(path)

    def build_base(self) -> list[str]:
        self.ensure_layout()
        base_dir = self.base_dir()
        self._clear_dir_contents(base_dir)
        if not self.enabled():
            return []
        copied: list[str] = []
        for source_path, relative_path in self.provider.collect_task_files(self.source_root):
            target_path = base_dir / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            copied.append(relative_path)
        self._write_attacker_manifest(base_dir, copied)
        self._write_snapshot(self.snapshots_dir() / "base.json", base_dir, tag="base")
        return copied

    def use_base_as_final(self) -> WorkspaceDiff:
        self.ensure_layout()
        diff = self._diff_dirs(self.base_dir(), self.final_dir())
        self._clear_dir_contents(self.final_dir())
        self._copy_dir_contents(self.base_dir(), self.final_dir())
        self._write_snapshot(self.snapshots_dir() / "final.json", self.final_dir(), tag="final")
        return diff

    def copy_base_to_attacker_output(self, attacker_name: str, phase: str, index: int = 1) -> str:
        output_dir = self.attacker_output_dir(attacker_name, phase, index)
        self._clear_dir_contents(output_dir)
        self._copy_dir_contents(self.base_dir(), output_dir)
        return str(output_dir)

    def finalize_from_attacker_output(
        self,
        attacker_name: str,
        phase: str,
        index: int = 1,
    ) -> tuple[WorkspaceDiff, list[str]]:
        self.ensure_layout()
        output_dir = self.attacker_output_dir(attacker_name, phase, index)
        final_dir = self.final_dir()
        ignored = self._disallowed_relative_paths(output_dir)
        diff = self._diff_dirs(self.base_dir(), output_dir, filter_allowed=True)
        self._clear_dir_contents(final_dir)
        self._copy_allowed_dir_contents(output_dir, final_dir)
        self._write_snapshot(self.snapshots_dir() / "final.json", final_dir, tag="final")
        return diff, ignored

    def materialize_final_to_workspace(self, workspace_dir: str) -> WorkspaceDiff:
        shared_root = Path(workspace_dir)
        shared_root.mkdir(parents=True, exist_ok=True)
        diff = self._diff_dirs(shared_root, self.final_dir(), filter_allowed=True)
        self._delete_allowed_files(shared_root)
        self._copy_dir_contents(self.final_dir(), shared_root)
        self._write_snapshot(self.snapshots_dir() / "materialized.json", shared_root, tag="materialized")
        return diff

    def _disallowed_relative_paths(self, root: Path) -> list[str]:
        if not self.enabled() or not root.exists():
            return []
        disallowed: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if not self.provider.is_allowed_relative_path(rel):
                disallowed.append(rel)
        return disallowed

    def _delete_allowed_files(self, root: Path) -> None:
        if not self.enabled() or not root.exists():
            return
        for path in sorted(root.rglob("*"), reverse=True):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if self.provider.is_allowed_relative_path(rel):
                path.unlink(missing_ok=True)
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue

    def _clear_dir_contents(self, path: Path) -> None:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

    def _copy_dir_contents(self, src: Path, dst: Path) -> None:
        if not src.exists():
            return
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            target = dst / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def _copy_allowed_dir_contents(self, src: Path, dst: Path) -> None:
        if not src.exists() or not self.enabled():
            return
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src).as_posix()
            if not self.provider.is_allowed_relative_path(rel):
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    def _diff_dirs(self, left: Path, right: Path, *, filter_allowed: bool = False) -> WorkspaceDiff:
        left_files = self._file_set(left, filter_allowed=filter_allowed)
        right_files = self._file_set(right, filter_allowed=filter_allowed)
        added = sorted(right_files - left_files)
        deleted = sorted(left_files - right_files)
        modified: list[str] = []
        for rel in sorted(left_files & right_files):
            if not self._files_equal(left / rel, right / rel):
                modified.append(rel.as_posix())
        return WorkspaceDiff(
            added=[path.as_posix() for path in added],
            modified=modified,
            deleted=[path.as_posix() for path in deleted],
        )

    def _file_set(self, root: Path, *, filter_allowed: bool = False) -> set[Path]:
        if not root.exists():
            return set()
        result: set[Path] = set()
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if filter_allowed and self.enabled() and not self.provider.is_allowed_relative_path(rel.as_posix()):
                continue
            result.add(rel)
        return result

    def _files_equal(self, left: Path, right: Path) -> bool:
        return left.read_bytes() == right.read_bytes()

    def _write_snapshot(self, path: Path, root: Path, *, tag: str) -> None:
        files = []
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(root).as_posix()
            if self.enabled() and not self.provider.is_allowed_relative_path(rel):
                continue
            files.append({"path": rel, "size": file_path.stat().st_size})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "framework": self.provider.framework if self.provider else "",
                    "tag": tag,
                    "root": str(root),
                    "files": files,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_attacker_manifest(self, base_dir: Path, discovered_files: list[str]) -> None:
        if not self.enabled() or self.provider is None:
            return
        payload = {
            "framework": self.provider.framework,
            "allowed_patterns": list(self.provider.allowed_patterns),
            "discovered_files": discovered_files,
            "attack_surfaces": [
                {
                    "kind": surface.kind,
                    "path_template": surface.path_template,
                    "description": surface.description,
                }
                for surface in self.provider.attacker_surfaces
            ],
        }
        manifest_path = base_dir / self.MANIFEST_FILE_NAME
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["ControlPlaneManager", "ControlPlaneProvider", "ControlSurfaceSpec", "create_control_plane_provider"]
