"""Tests for the evaluation gates field (§3k, added in v0.7.0)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentversion.manifest import EvalGate


def _ts() -> str:
    return datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc).isoformat()


def _minimal_manifest(*, evaluation: dict = None) -> dict:
    data = {
        "spec_version": "0.7.0",
        "kind": "agent_manifest",
        "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
        "agent_name": "test",
        "version_label": "v1",
        "created_at": "2026-01-01T00:00:00Z",
        "identity": {"overall_hash": "sha256:abc", "hash_algorithm": "jcs-sha256"},
        "contract": {
            "prompt_stack": {},
            "model_runtime": {"provider": "openai", "model": "gpt-4o"},
            "tool_registry": {"registry_version": "1", "registry_hash": "sha256:r", "tools": []},
            "workflow": {"graph_name": "g"},
            "output_contract": {
                "version": "1", "schema_hash": "sha256:o",
                "format": "text", "strict": False,
            },
        },
    }
    if evaluation is not None:
        data["evaluation"] = evaluation
    return data


# ── Model parsing ──────────────────────────────────────


class TestEvalGateModel:
    def test_min_direction_default(self):
        g = EvalGate(
            name="regression",
            threshold=0.95,
            actual_score=0.972,
            passed=True,
            ran_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        )
        assert g.threshold_direction == "min"
        assert g.passed is True

    def test_max_direction(self):
        g = EvalGate(
            name="latency",
            threshold=5000,
            actual_score=4180,
            threshold_direction="max",
            passed=True,
            ran_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        )
        assert g.threshold_direction == "max"

    def test_invalid_direction(self):
        with pytest.raises(Exception):
            EvalGate(
                name="x", threshold=1.0, actual_score=1.0,
                threshold_direction="not_a_direction",  # type: ignore[arg-type]
                passed=True, ran_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
            )


# ── Validator semantics ────────────────────────────────


class TestEvalGateConsistency:
    def test_consistent_min_passing(self):
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(evaluation={
            "gates": [
                {
                    "name": "regression", "threshold": 0.95, "actual_score": 0.972,
                    "passed": True, "ran_at": _ts(),
                }
            ]
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "eval_gate_inconsistent" not in codes

    def test_inconsistent_min_warns(self):
        # threshold=0.95, actual=0.92 → should be passed=False, but says passed=True
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(evaluation={
            "gates": [
                {
                    "name": "regression", "threshold": 0.95, "actual_score": 0.92,
                    "passed": True, "ran_at": _ts(),
                }
            ]
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.warnings}
        assert "eval_gate_inconsistent" in codes

    def test_max_direction(self):
        # threshold=5000ms latency, actual=4180 → passed=True (lower is better)
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(evaluation={
            "gates": [
                {
                    "name": "latency", "threshold": 5000, "actual_score": 4180,
                    "threshold_direction": "max", "passed": True, "ran_at": _ts(),
                }
            ]
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "eval_gate_inconsistent" not in codes

    def test_max_direction_inconsistent(self):
        # threshold=5000ms latency, actual=6000 → should be passed=False
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(evaluation={
            "gates": [
                {
                    "name": "latency", "threshold": 5000, "actual_score": 6000,
                    "threshold_direction": "max", "passed": True, "ran_at": _ts(),
                }
            ]
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.warnings}
        assert "eval_gate_inconsistent" in codes


# ── Hash isolation ─────────────────────────────────────


class TestEvaluationHashIsolation:
    def test_adding_evaluation_doesnt_change_hash(self):
        from agentversion.hasher import hash_manifest

        without = _minimal_manifest()
        with_ev = _minimal_manifest(evaluation={
            "gates": [
                {
                    "name": "regression", "threshold": 0.95, "actual_score": 0.972,
                    "passed": True, "ran_at": _ts(),
                }
            ]
        })
        assert hash_manifest(without) == hash_manifest(with_ev)

    def test_re_running_eval_doesnt_change_hash(self):
        from agentversion.hasher import hash_manifest

        e1 = _minimal_manifest(evaluation={
            "gates": [{"name": "r", "threshold": 0.9, "actual_score": 0.93, "passed": True, "ran_at": _ts()}]
        })
        e2 = _minimal_manifest(evaluation={
            "gates": [{"name": "r", "threshold": 0.9, "actual_score": 0.95, "passed": True, "ran_at": _ts()}]
        })
        # Different score, same contract → same hash
        assert hash_manifest(e1) == hash_manifest(e2)
