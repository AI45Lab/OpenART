from __future__ import annotations

import json
from pathlib import PurePosixPath
import shlex

from framework.attackers.base import AttackerBase
from framework.attackers.models import AttackerContext, AttackerResult


PLUGIN_ARTIFACT_DIR = ".openart_attacker_artifacts"


class GenericCommandAttacker(AttackerBase):
    def _read_container_text_optional(self, path: str) -> str:
        resolved = str(path or "").strip()
        if not resolved:
            return ""
        try:
            return self.container.read_text_file(resolved, env=self.runtime_env)
        except Exception:
            return ""

    def _skill_validation_feedback_markdown(self, context: AttackerContext) -> str:
        feedback_dir = str(context.feedback_dir or self.runtime_env.get("OPENART_FEEDBACK_DIR", "") or "").rstrip("/")
        if not feedback_dir:
            return ""
        candidates = [
            f"{feedback_dir}/skill_validation.json",
            f"{feedback_dir}/control/target/snapshots/skill_validation.json",
        ]
        payload: dict[str, object] = {}
        for path in candidates:
            text = self._read_container_text_optional(path)
            if not text:
                continue
            try:
                loaded = json.loads(text)
            except Exception:
                continue
            if isinstance(loaded, dict) and loaded.get("rejected"):
                payload = loaded
                break
        rejected = payload.get("rejected") if isinstance(payload, dict) else None
        if not isinstance(rejected, list) or not rejected:
            return ""
        return (
            "## Previous Skill Validation Failures\n\n"
            "Framework-side skill validation rejected generated skill wrappers. "
            "Repair these exact folders before changing strategy. Use each item's "
            "`reasons` and `suggested_fix`, then run `openart.validate_target_skills` "
            "until the validation JSON has no `rejected` entries.\n\n"
            "```json\n"
            + json.dumps(rejected[:8], ensure_ascii=False, indent=2)
            + "\n```"
        )

    def _synthesize_attacker_instruction_file(self, context: AttackerContext, attack_iteration: int) -> str:
        original_path = str(context.attacker_instruction_file or "").strip()
        original_text = self._read_container_text_optional(original_path)
        if not original_text:
            return original_path

        additions: list[str] = []
        guide_path = str(self.runtime_env.get("OPENART_TOOL_GUIDE_FILE", "") or "").strip()
        guide_text = self._read_container_text_optional(guide_path)
        if guide_text.strip():
            additions.append("## Managed Tool Guidance\n\n" + guide_text.strip())
        validation_feedback = self._skill_validation_feedback_markdown(context)
        if validation_feedback:
            additions.append(validation_feedback)
        if not additions:
            return original_path

        merged = original_text.rstrip() + "\n\n" + "\n\n".join(additions).rstrip() + "\n"
        synthesized_path = f"{self._state_dir()}/instructions/attacker_iter_{attack_iteration:03d}.md"
        try:
            self.container.ensure_dir(f"{self._state_dir()}/instructions", env=self.runtime_env)
            self.container.write_text_file(synthesized_path, merged, env=self.runtime_env)
        except Exception as exc:
            self._write_artifact(
                "attacker_instruction_synthesis_error.txt",
                f"failed to write synthesized attacker instruction: {exc}\n",
                attack_iteration=attack_iteration,
            )
            return original_path
        self.runtime_env["OPENART_SYNTHESIZED_ATTACKER_INSTRUCTION_FILE"] = synthesized_path
        self._write_artifact("synthesized_attacker_instruction.md", merged, attack_iteration=attack_iteration)
        return synthesized_path

    def _capture_plugin_artifacts(self, context: AttackerContext, attack_iteration: int) -> None:
        root = f"{context.output_workspace_dir.rstrip('/')}/{PLUGIN_ARTIFACT_DIR}"
        quoted_root = shlex.quote(root)
        code, stdout, stderr = self.container.exec(
            [
                "/bin/sh",
                "-lc",
                f"if [ -d {quoted_root} ]; then find {quoted_root} -type f -size -1048576c -print; fi",
            ],
            env=self.runtime_env,
        )
        if code != 0:
            self._write_artifact("plugin_artifacts_error.txt", stderr, attack_iteration=attack_iteration)
            return
        errors: list[str] = []
        for raw_path in stdout.splitlines():
            path = raw_path.strip()
            if not path or not path.startswith(root.rstrip("/") + "/"):
                continue
            rel = path[len(root.rstrip("/") + "/") :]
            rel_path = PurePosixPath(rel)
            if rel_path.is_absolute() or any(part in {"", ".", ".."} for part in rel_path.parts):
                errors.append(f"skipped unsafe artifact path: {rel}")
                continue
            try:
                content = self.container.read_text_file(path, env=self.runtime_env)
            except Exception as exc:
                errors.append(f"{rel}: {exc}")
                continue
            self._write_artifact(rel_path.as_posix(), content, attack_iteration=attack_iteration)
        if errors:
            self._write_artifact("plugin_artifacts_error.txt", "\n".join(errors) + "\n", attack_iteration=attack_iteration)

    def run(self, context: AttackerContext) -> AttackerResult:
        attacker_instruction_file = self._synthesize_attacker_instruction_file(
            context,
            attack_iteration=context.attack_iteration,
        )
        placeholders = {
            "{{target_instruction_file}}": context.target_instruction_file,
            "{{attacker_instruction_file}}": attacker_instruction_file,
            "{{shared_workspace_dir}}": context.shared_workspace_dir,
            "{{input_workspace_dir}}": context.input_workspace_dir,
            "{{output_workspace_dir}}": context.output_workspace_dir,
            "{{input_target_control_dir}}": context.input_target_control_dir,
            "{{output_target_control_dir}}": context.output_target_control_dir,
            "{{feedback_dir}}": context.feedback_dir,
            "{{trace_file}}": context.trace_file,
            "{{evaluator_inputs_dir}}": context.evaluator_inputs_dir,
            "{{evaluator_outputs_dir}}": context.evaluator_outputs_dir,
            "{{target_runner_outputs_dir}}": context.target_runner_outputs_dir,
            "{{evaluation_iterations_dir}}": context.evaluation_iterations_dir,
            "{{attacker_history_dir}}": context.attacker_history_dir,
            "{{attack_iteration}}": str(context.attack_iteration),
            "{{feedback_iteration}}": str(context.feedback_iteration),
            "{{task_dir}}": context.task_dir,
            "{{run_id}}": context.run_id,
            "{{attack_phase}}": context.phase,
        }

        parts = [self.spec.cmd] + list(self.spec.args)
        expanded = []
        for part in parts:
            value = str(part)
            for marker, replacement in placeholders.items():
                value = value.replace(marker, replacement)
            expanded.append(value)

        with self._timing_event("render_command", category="attacker", attack_iteration=context.attack_iteration) as event:
            command = " ".join(shlex.quote(part) for part in expanded if part)
            if event is not None:
                event.metadata["command_length"] = len(command)
        with self._timing_event("workspace_listing_before", category="workspace", attack_iteration=context.attack_iteration):
            self._capture_workspace_listing("before_run", attack_iteration=context.attack_iteration)
        if context.output_target_control_dir:
            control_dir = shlex.quote(context.output_target_control_dir)
            with self._timing_event(
                "control_listing_before",
                category="workspace",
                attack_iteration=context.attack_iteration,
                metadata={"control_dir": context.output_target_control_dir},
            ) as event:
                code, stdout, stderr = self.container.exec(["/bin/sh", "-lc", f"ls -laR {control_dir}"], env=self.runtime_env)
                if event is not None:
                    event.metadata["exit_code"] = code
                    if code != 0:
                        event.mark("error")
                self._write_artifact(
                    "control_before_run_ls.txt",
                    stdout if code == 0 else stderr,
                    attack_iteration=context.attack_iteration,
                )
        with self._timing_event("write_command_artifact", category="artifact", attack_iteration=context.attack_iteration):
            self._write_artifact("command.sh", command + "\n", attack_iteration=context.attack_iteration)
        self._trace(context.run_id, "run_start", "attacker_start", {"name": self.spec.name, "phase": self.spec.phase})
        with self._timing_event(
            "docker_exec_command",
            category="docker_exec",
            attack_iteration=context.attack_iteration,
            metadata={
                "container_name": self.container.spec.name,
                "timeout_seconds": self.spec.timeout_seconds,
            },
        ) as event:
            code, stdout, stderr = self.container.exec(
                ["/bin/bash", "-lc", command],
                env=self.runtime_env,
                timeout_seconds=self.spec.timeout_seconds,
            )
            if event is not None:
                event.metadata["exit_code"] = code
                event.metadata["stdout_bytes"] = len(stdout.encode("utf-8", errors="ignore"))
                event.metadata["stderr_bytes"] = len(stderr.encode("utf-8", errors="ignore"))
                if code != 0:
                    event.mark("error")
        with self._timing_event(
            "write_stdout_stderr",
            category="artifact",
            attack_iteration=context.attack_iteration,
            metadata={
                "exit_code": code,
                "stdout_bytes": len(stdout.encode("utf-8", errors="ignore")),
                "stderr_bytes": len(stderr.encode("utf-8", errors="ignore")),
            },
        ):
            self._write_artifact("stdout.txt", stdout, attack_iteration=context.attack_iteration)
            self._write_artifact("stderr.txt", stderr, attack_iteration=context.attack_iteration)
        with self._timing_event("write_status", category="artifact", attack_iteration=context.attack_iteration, metadata={"exit_code": code}):
            self._write_status(code, attack_iteration=context.attack_iteration)
        with self._timing_event("capture_plugin_artifacts", category="artifact", attack_iteration=context.attack_iteration):
            self._capture_plugin_artifacts(context, attack_iteration=context.attack_iteration)
        self._log_output(stdout, stderr, code)
        with self._timing_event("workspace_listing_after", category="workspace", attack_iteration=context.attack_iteration):
            self._capture_workspace_listing("after_run", attack_iteration=context.attack_iteration)
        if context.output_target_control_dir:
            control_dir = shlex.quote(context.output_target_control_dir)
            with self._timing_event(
                "control_listing_after",
                category="workspace",
                attack_iteration=context.attack_iteration,
                metadata={"control_dir": context.output_target_control_dir},
            ) as event:
                list_code, list_stdout, list_stderr = self.container.exec(["/bin/sh", "-lc", f"ls -laR {control_dir}"], env=self.runtime_env)
                if event is not None:
                    event.metadata["exit_code"] = list_code
                    if list_code != 0:
                        event.mark("error")
                self._write_artifact(
                    "control_after_run_ls.txt",
                    list_stdout if list_code == 0 else list_stderr,
                    attack_iteration=context.attack_iteration,
                )
        self._trace(
            context.run_id,
            "run_end",
            "attacker_end",
            {"name": self.spec.name, "phase": self.spec.phase, "exit_code": code},
        )
        return AttackerResult(
            run_id=context.run_id,
            attacker_name=self.spec.name,
            phase=self.spec.phase,
            exit_code=code,
            output_workspace_dir=context.output_workspace_dir,
        )
