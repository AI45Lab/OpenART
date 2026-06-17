"""Unit tests for TaskBundleSpec model."""
from __future__ import annotations

import pytest

from framework.attackers.models import AttackerSpec
from framework.models.task import TaskBundleSpec


class TestTaskBundleSpec:
    """Tests for TaskBundleSpec dataclass."""

    def test_task_bundle_spec_with_required_fields(self, minimal_task_bundle_spec: TaskBundleSpec):
        """Test TaskBundleSpec with only required fields."""
        assert minimal_task_bundle_spec.task_id == "minimal-task"
        assert minimal_task_bundle_spec.name == "Minimal Task"
        assert minimal_task_bundle_spec.root_dir == "/tasks/minimal"
        assert minimal_task_bundle_spec.dockerfile == "Dockerfile"
        assert minimal_task_bundle_spec.context_dir == "."
        assert minimal_task_bundle_spec.target_instruction == "Do something"

    def test_task_bundle_spec_optional_fields_defaults(self, minimal_task_bundle_spec: TaskBundleSpec):
        """Test that optional fields have correct defaults."""
        assert minimal_task_bundle_spec.attacker is None
        assert minimal_task_bundle_spec.required_services == []
        assert minimal_task_bundle_spec.extra_services == []
        assert minimal_task_bundle_spec.seed_dir is None
        assert minimal_task_bundle_spec.deterministic_eval is None
        assert minimal_task_bundle_spec.judge_rubric is None
        assert minimal_task_bundle_spec.timeout_seconds == 1800

    def test_task_bundle_spec_with_all_fields(self, sample_task_bundle_spec: TaskBundleSpec):
        """Test TaskBundleSpec with all fields populated."""
        assert sample_task_bundle_spec.task_id == "task-001"
        assert sample_task_bundle_spec.name == "Test Task"
        assert sample_task_bundle_spec.root_dir == "/tasks/test"
        assert sample_task_bundle_spec.dockerfile == "Dockerfile"
        assert sample_task_bundle_spec.context_dir == "."
        assert sample_task_bundle_spec.target_instruction == "Solve the problem"
        assert sample_task_bundle_spec.attacker is not None
        assert sample_task_bundle_spec.attacker.instruction == "Exploit the vulnerability"
        assert sample_task_bundle_spec.required_services == ["database"]
        assert sample_task_bundle_spec.extra_services == ["cache"]
        assert sample_task_bundle_spec.seed_dir == "/seeds"
        assert sample_task_bundle_spec.deterministic_eval == "exact_match"
        assert sample_task_bundle_spec.judge_rubric == "Check for correctness"
        assert sample_task_bundle_spec.timeout_seconds == 3600

    def test_task_bundle_spec_timeout_default(self):
        """Test that timeout_seconds defaults to 1800 (30 minutes)."""
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Test",
        )
        assert task.timeout_seconds == 1800

    def test_task_bundle_spec_custom_timeout(self):
        """Test TaskBundleSpec with custom timeout."""
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Test",
            timeout_seconds=7200,  # 2 hours
        )
        assert task.timeout_seconds == 7200

    def test_task_bundle_spec_with_services(self):
        """Test TaskBundleSpec with required and extra services."""
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Test",
            required_services=["database", "queue"],
            extra_services=["cache", "monitoring"],
        )
        assert len(task.required_services) == 2
        assert len(task.extra_services) == 2
        assert "database" in task.required_services
        assert "cache" in task.extra_services

    def test_task_bundle_spec_with_attacker(self):
        """Test TaskBundleSpec with attacker configuration."""
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Defend the system",
            attacker=AttackerSpec(
                name="custom-attacker",
                instruction="Try to bypass the security",
                cmd="python3",
                args=["attacker.py"],
            ),
        )
        assert task.attacker is not None
        assert task.attacker.instruction == "Try to bypass the security"

    def test_attacker_vector_permissions_helpers(self):
        attacker = AttackerSpec(
            name="custom-attacker",
            instruction="attack.md",
            cmd="python3",
            feedback_loop=True,
            vector_permissions=["workspace_files", "claude_md", "claude_md"],
        )

        assert attacker.normalized_vector_permissions() == ("workspace_files", "claude_md")
        assert attacker.allows_workspace_files() is True
        assert attacker.allowed_control_vectors() == ("claude_md",)
        assert attacker.feedback_loop is True

    def test_task_bundle_spec_without_attacker(self):
        """Test TaskBundleSpec without attacker configuration (defense-only task)."""
        task = TaskBundleSpec(
            task_id="defense-only",
            name="Defense Only",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Just do the work",
        )
        assert task.attacker is None

    def test_task_bundle_spec_with_deterministic_eval(self):
        """Test TaskBundleSpec with deterministic evaluation."""
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Test",
            deterministic_eval="exact_match",
        )
        assert task.deterministic_eval == "exact_match"

    def test_task_bundle_spec_with_judge_rubric(self):
        """Test TaskBundleSpec with judge rubric."""
        rubric = "Evaluate based on:\n1. Correctness\n2. Efficiency\n3. Code quality"
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Test",
            judge_rubric=rubric,
        )
        assert "Correctness" in task.judge_rubric

    def test_task_bundle_spec_with_seed_dir(self):
        """Test TaskBundleSpec with seed directory."""
        task = TaskBundleSpec(
            task_id="test",
            name="Test",
            root_dir="/test",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Test",
            seed_dir="/seeds/test",
        )
        assert task.seed_dir == "/seeds/test"

    def test_task_bundle_spec_multiple_instances_independent(self):
        """Test that multiple TaskBundleSpec instances are independent."""
        task1 = TaskBundleSpec(
            task_id="task-1",
            name="Task 1",
            root_dir="/task1",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Task 1",
            required_services=["db"],
        )
        task2 = TaskBundleSpec(
            task_id="task-2",
            name="Task 2",
            root_dir="/task2",
            dockerfile="Dockerfile",
            context_dir=".",
            target_instruction="Task 2",
            required_services=["queue"],
        )
        assert task1.task_id != task2.task_id
        assert task1.required_services == ["db"]
        assert task2.required_services == ["queue"]
