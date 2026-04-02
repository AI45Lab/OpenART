"""Unit tests for EvaluatorResult model."""
from __future__ import annotations

import pytest

from framework.models.specs import EvaluatorResult


class TestEvaluatorResult:
    """Tests for EvaluatorResult dataclass."""

    def test_evaluator_result_with_minimal_fields(self, minimal_evaluator_result: EvaluatorResult):
        """Test EvaluatorResult with minimal required fields."""
        assert minimal_evaluator_result.run_id == "run-001"
        assert minimal_evaluator_result.decision == "fail"
        assert minimal_evaluator_result.score == 0.0
        assert minimal_evaluator_result.subscores == {}
        assert minimal_evaluator_result.rationale == ""
        assert minimal_evaluator_result.artifacts == {}
        assert minimal_evaluator_result.metadata == {}

    def test_evaluator_result_with_all_fields(self, sample_evaluator_result: EvaluatorResult):
        """Test EvaluatorResult with all fields populated."""
        assert sample_evaluator_result.run_id == "run-001"
        assert sample_evaluator_result.decision == "pass"
        assert sample_evaluator_result.score == 0.95
        assert sample_evaluator_result.subscores == {"accuracy": 0.9, "completeness": 1.0}
        assert sample_evaluator_result.rationale == "All checks passed"
        assert sample_evaluator_result.artifacts == {"log": "/logs/run-001.log"}
        assert sample_evaluator_result.metadata == {"evaluator": "llm-judge", "model": "claude-3"}

    def test_evaluator_result_default_collections(self):
        """Test that default collections are empty dicts."""
        result = EvaluatorResult(run_id="test", decision="unknown", score=0.5)
        assert result.subscores == {}
        assert result.artifacts == {}
        assert result.metadata == {}

    def test_evaluator_result_decision_values(self):
        """Test EvaluatorResult with different decision values."""
        for decision in ["pass", "fail", "unknown"]:
            result = EvaluatorResult(run_id="test", decision=decision, score=0.5)
            assert result.decision == decision

    def test_evaluator_result_score_range(self):
        """Test EvaluatorResult with various score values."""
        # Score 0.0
        result = EvaluatorResult(run_id="test", decision="fail", score=0.0)
        assert result.score == 0.0

        # Score 1.0
        result = EvaluatorResult(run_id="test", decision="pass", score=1.0)
        assert result.score == 1.0

        # Score 0.5
        result = EvaluatorResult(run_id="test", decision="unknown", score=0.5)
        assert result.score == 0.5

    def test_evaluator_result_with_subscores(self):
        """Test EvaluatorResult with subscores."""
        result = EvaluatorResult(
            run_id="test",
            decision="pass",
            score=0.85,
            subscores={
                "accuracy": 0.9,
                "completeness": 0.8,
                "correctness": 0.85,
            },
        )
        assert len(result.subscores) == 3
        assert result.subscores["accuracy"] == 0.9
        assert result.subscores["completeness"] == 0.8
        assert result.subscores["correctness"] == 0.85

    def test_evaluator_result_with_rationale(self):
        """Test EvaluatorResult with rationale."""
        result = EvaluatorResult(
            run_id="test",
            decision="fail",
            score=0.3,
            rationale="The solution did not meet the required criteria for correctness.",
        )
        assert "did not meet" in result.rationale

    def test_evaluator_result_with_artifacts(self):
        """Test EvaluatorResult with artifacts."""
        result = EvaluatorResult(
            run_id="test",
            decision="pass",
            score=0.9,
            artifacts={
                "log": "/logs/test.log",
                "screenshot": "/artifacts/screenshot.png",
                "report": "/reports/test_report.pdf",
            },
        )
        assert result.artifacts["log"] == "/logs/test.log"
        assert result.artifacts["screenshot"] == "/artifacts/screenshot.png"
        assert result.artifacts["report"] == "/reports/test_report.pdf"

    def test_evaluator_result_with_metadata(self):
        """Test EvaluatorResult with metadata."""
        result = EvaluatorResult(
            run_id="test",
            decision="pass",
            score=0.95,
            metadata={
                "evaluator": "llm-judge",
                "model": "claude-opus-4-6",
                "temperature": 0.0,
                "timestamp": 1234567890,
            },
        )
        assert result.metadata["evaluator"] == "llm-judge"
        assert result.metadata["model"] == "claude-opus-4-6"

    def test_evaluator_result_multiple_instances_independent(self):
        """Test that multiple EvaluatorResult instances are independent."""
        result1 = EvaluatorResult(
            run_id="run-001",
            decision="pass",
            score=0.9,
            metadata={"key": "value1"},
        )
        result2 = EvaluatorResult(
            run_id="run-002",
            decision="fail",
            score=0.1,
            metadata={"key": "value2"},
        )
        assert result1.metadata["key"] == "value1"
        assert result2.metadata["key"] == "value2"
        assert result1.run_id != result2.run_id

    def test_evaluator_result_rationale_empty_default(self):
        """Test that rationale defaults to empty string."""
        result = EvaluatorResult(run_id="test", decision="unknown", score=0.5)
        assert result.rationale == ""

    def test_evaluator_result_rationale_with_multiline(self):
        """Test EvaluatorResult with multiline rationale."""
        rationale = """Line 1: Check passed
Line 2: Verification complete
Line 3: All tests succeeded"""
        result = EvaluatorResult(
            run_id="test",
            decision="pass",
            score=1.0,
            rationale=rationale,
        )
        assert "\n" in result.rationale
        assert "Line 1" in result.rationale