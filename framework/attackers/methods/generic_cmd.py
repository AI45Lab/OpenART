from __future__ import annotations

import shlex

from framework.attackers.base import AttackerBase
from framework.attackers.models import AttackerContext, AttackerResult


class GenericCommandAttacker(AttackerBase):
    def run(self, context: AttackerContext) -> AttackerResult:
        placeholders = {
            "{{target_instruction_file}}": context.target_instruction_file,
            "{{attacker_instruction_file}}": context.attacker_instruction_file,
            "{{shared_workspace_dir}}": context.shared_workspace_dir,
            "{{input_workspace_dir}}": context.input_workspace_dir,
            "{{output_workspace_dir}}": context.output_workspace_dir,
            "{{input_target_control_dir}}": context.input_target_control_dir,
            "{{output_target_control_dir}}": context.output_target_control_dir,
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

        command = " ".join(shlex.quote(part) for part in expanded if part)
        self._capture_workspace_listing("before_run")
        if context.output_target_control_dir:
            control_dir = shlex.quote(context.output_target_control_dir)
            code, stdout, stderr = self.container.exec(["/bin/sh", "-lc", f"ls -laR {control_dir}"], env=self.runtime_env)
            self._write_artifact("control_before_run_ls.txt", stdout if code == 0 else stderr)
        self._write_artifact("command.sh", command + "\n")
        self._trace(context.run_id, "run_start", "attacker_start", {"name": self.spec.name, "phase": self.spec.phase})
        code, stdout, stderr = self.container.exec(["/bin/bash", "-lc", command], env=self.runtime_env)
        self._write_artifact("stdout.txt", stdout)
        self._write_artifact("stderr.txt", stderr)
        self._write_status(code)
        self._log_output(stdout, stderr, code)
        self._capture_workspace_listing("after_run")
        if context.output_target_control_dir:
            control_dir = shlex.quote(context.output_target_control_dir)
            list_code, list_stdout, list_stderr = self.container.exec(["/bin/sh", "-lc", f"ls -laR {control_dir}"], env=self.runtime_env)
            self._write_artifact("control_after_run_ls.txt", list_stdout if list_code == 0 else list_stderr)
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
