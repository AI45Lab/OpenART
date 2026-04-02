from __future__ import annotations

import filecmp
import hashlib
import json
import shutil
from pathlib import Path

from framework.models.specs import WorkspaceDiff


class WorkspaceManager:
    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir)

    def _run_dir(self, run_id: str) -> Path:
        _ = run_id
        return self.root_dir

    def shared_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "shared"

    def attackers_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "attackers"

    def attacker_output_dir(self, run_id: str, attacker_name: str, phase: str, index: int = 1) -> Path:
        return self.attackers_dir(run_id) / attacker_name / f"{phase}_{index:03d}"

    def ensure_run_layout(self, run_id: str) -> None:
        self.shared_dir(run_id).mkdir(parents=True, exist_ok=True)
        self.attackers_dir(run_id).mkdir(parents=True, exist_ok=True)

    def ensure_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1) -> str:
        path = self.attacker_output_dir(run_id, attacker_name, phase, index)
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def snapshot_shared(self, run_id: str, tag: str) -> dict[str, object]:
        shared_dir = self.shared_dir(run_id)
        files: list[dict[str, object]] = []
        for path in sorted(shared_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(shared_dir).as_posix()
            files.append({"path": rel, "size": path.stat().st_size, "sha256": self._sha256(path)})
        snapshot = {
            "run_id": run_id,
            "tag": tag,
            "shared_dir": str(shared_dir),
            "files": files,
        }
        snapshot_path = self._run_dir(run_id) / "snapshots" / f"shared_{tag}.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return snapshot

    def copy_shared_to_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1) -> str:
        shared_dir = self.shared_dir(run_id)
        output_dir = self.attacker_output_dir(run_id, attacker_name, phase, index)
        self._clear_dir_contents(output_dir)
        self._copy_dir_contents(shared_dir, output_dir)
        return str(output_dir)

    def diff_attacker_output_against_shared(self, run_id: str, attacker_name: str, phase: str, index: int = 1) -> WorkspaceDiff:
        shared_dir = self.shared_dir(run_id)
        output_dir = self.attacker_output_dir(run_id, attacker_name, phase, index)

        shared_files = self._file_set(shared_dir)
        output_files = self._file_set(output_dir)
        added = sorted(output_files - shared_files)
        deleted = sorted(shared_files - output_files)
        modified: list[str] = []
        for rel in sorted(shared_files & output_files):
            if not filecmp.cmp(shared_dir / rel, output_dir / rel, shallow=False):
                modified.append(rel.as_posix())
        return WorkspaceDiff(
            added=[path.as_posix() for path in added],
            modified=modified,
            deleted=[path.as_posix() for path in deleted],
        )

    def replace_shared_with_attacker_output(self, run_id: str, attacker_name: str, phase: str, index: int = 1) -> WorkspaceDiff:
        shared_dir = self.shared_dir(run_id)
        output_dir = self.attacker_output_dir(run_id, attacker_name, phase, index)
        diff = self.diff_attacker_output_against_shared(run_id, attacker_name, phase, index)
        self._clear_dir_contents(shared_dir)
        self._copy_dir_contents(output_dir, shared_dir)
        return diff

    def cleanup_run(self, run_id: str) -> None:
        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)

    def _clear_dir_contents(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for child in path.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

    def _copy_dir_contents(self, src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
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

    def _file_set(self, root: Path) -> set[Path]:
        if not root.exists():
            return set()
        return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()


class TargetOutputStore:
    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir)

    def _iter_dir(self, run_id: str, iteration: int) -> Path:
        return self.root_dir / run_id / "target_output" / f"iter_{iteration:03d}"

    def write_output(self, run_id: str, iteration: int, content: str) -> None:
        iter_dir = self._iter_dir(run_id, iteration)
        iter_dir.mkdir(parents=True, exist_ok=True)
        (iter_dir / "final_message.txt").write_text(content, encoding="utf-8")

    def write_artifacts(
        self,
        run_id: str,
        iteration: int,
        stdout: str,
        stderr: str,
        final_message: str,
        metadata: dict,
    ) -> None:
        iter_dir = self._iter_dir(run_id, iteration)
        iter_dir.mkdir(parents=True, exist_ok=True)
        (iter_dir / "stdout.txt").write_text(stdout, encoding="utf-8")
        (iter_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
        (iter_dir / "final_message.txt").write_text(final_message, encoding="utf-8")
        (iter_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_output_path(self, run_id: str, iteration: int) -> str:
        return str(self._iter_dir(run_id, iteration))

    def cleanup_run(self, run_id: str) -> None:
        run_dir = self.root_dir / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)


__all__ = ["TargetOutputStore", "WorkspaceManager"]
