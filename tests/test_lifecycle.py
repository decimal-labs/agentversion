"""Tests for the lifecycle + tombstone fields (§3e, §3j, added in v0.7.0)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agentversion.manifest import (
    Lifecycle,
    LifecycleTransition,
)


def _ts(h: int = 0) -> datetime:
    """A reproducible timestamp h hours after a fixed epoch."""
    return datetime(2026, 5, 1, tzinfo=timezone.utc) + timedelta(hours=h)


# ── Model parsing ──────────────────────────────────────


class TestLifecycleModel:
    def test_minimal(self):
        lc = Lifecycle(current_stage="draft")
        assert lc.current_stage == "draft"
        assert lc.history == []
        assert lc.supersedes == []
        assert lc.superseded_by is None
        assert lc.sunset_at is None

    def test_full(self):
        lc = Lifecycle(
            current_stage="production",
            history=[
                LifecycleTransition(stage="draft", transitioned_at=_ts(0), by="user:stanley"),
                LifecycleTransition(stage="candidate", transitioned_at=_ts(24), by="system:ci"),
                LifecycleTransition(
                    stage="production",
                    transitioned_at=_ts(48),
                    by="system:release-bot",
                    eval_ref="regression-suite",
                    approved_by=["user:stanley", "user:eng-on-call"],
                    notes="Promoted after 4-day soak.",
                ),
            ],
            supersedes=["amf_01HZJ9OLDONE"],
        )
        assert len(lc.history) == 3
        assert lc.history[-1].approved_by == ["user:stanley", "user:eng-on-call"]
        assert lc.supersedes == ["amf_01HZJ9OLDONE"]

    def test_invalid_stage(self):
        with pytest.raises(Exception):
            Lifecycle(current_stage="not_a_stage")  # type: ignore[arg-type]


# ── Validator semantics ────────────────────────────────


def _minimal_manifest(**lifecycle_kwargs) -> dict:
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
    if lifecycle_kwargs:
        data["lifecycle"] = lifecycle_kwargs
    return data


class TestLifecycleValidator:
    def test_history_unsorted_is_error(self):
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(
            current_stage="production",
            history=[
                {"stage": "candidate", "transitioned_at": _ts(24).isoformat(), "by": "system:ci"},
                {"stage": "draft", "transitioned_at": _ts(0).isoformat(), "by": "user:stanley"},
                {"stage": "production", "transitioned_at": _ts(48).isoformat(), "by": "system:rb"},
            ],
        )
        result = validate_manifest(data, check_hash=False)
        assert result.valid is False
        codes = {i.code for i in result.errors}
        assert "lifecycle_history_unsorted" in codes

    def test_current_stage_must_match_last_history(self):
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(
            current_stage="production",
            history=[
                {"stage": "draft", "transitioned_at": _ts(0).isoformat(), "by": "user:stanley"},
                {"stage": "staging", "transitioned_at": _ts(24).isoformat(), "by": "system:ci"},
            ],
        )
        result = validate_manifest(data, check_hash=False)
        assert result.valid is False
        codes = {i.code for i in result.errors}
        assert "lifecycle_stage_mismatch" in codes

    def test_valid_lifecycle_passes(self):
        from agentversion.validator import validate_manifest

        data = _minimal_manifest(
            current_stage="production",
            history=[
                {"stage": "draft", "transitioned_at": _ts(0).isoformat(), "by": "user:stanley"},
                {"stage": "candidate", "transitioned_at": _ts(24).isoformat(), "by": "system:ci"},
                {"stage": "production", "transitioned_at": _ts(48).isoformat(), "by": "system:rb"},
            ],
        )
        result = validate_manifest(data, check_hash=False)
        lc_issues = [i for i in result.issues if i.code.startswith("lifecycle_")]
        assert lc_issues == []
        assert result.valid is True

    def test_status_lifecycle_agreement(self):
        from agentversion.validator import validate_manifest

        # status=active, lifecycle.current_stage=production → agrees (active maps to candidate/staging/production)
        data = _minimal_manifest(current_stage="production")
        data["status"] = "active"
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "lifecycle_status_mismatch" not in codes

    def test_status_lifecycle_disagreement(self):
        from agentversion.validator import validate_manifest

        # status=draft, lifecycle.current_stage=production → disagrees
        data = _minimal_manifest(current_stage="production")
        data["status"] = "draft"
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.warnings}
        assert "lifecycle_status_mismatch" in codes


# ── Hash isolation ─────────────────────────────────────


class TestLifecycleHashIsolation:
    """Lifecycle must NOT participate in identity.overall_hash."""

    def test_adding_lifecycle_doesnt_change_hash(self):
        from agentversion.hasher import hash_manifest

        without = _minimal_manifest()
        with_lc = _minimal_manifest(
            current_stage="production",
            history=[
                {"stage": "draft", "transitioned_at": _ts(0).isoformat(), "by": "user:stanley"},
                {"stage": "production", "transitioned_at": _ts(48).isoformat(), "by": "system:rb"},
            ],
        )
        assert hash_manifest(without) == hash_manifest(with_lc)

    def test_changing_lifecycle_doesnt_change_hash(self):
        from agentversion.hasher import hash_manifest

        v1 = _minimal_manifest(current_stage="candidate")
        v2 = _minimal_manifest(current_stage="production")
        assert hash_manifest(v1) == hash_manifest(v2)


# ── Tombstone (§3j) ────────────────────────────────────


class TestTombstone:
    def test_yanked_fields_optional(self):
        from agentversion.manifest import AgentManifest

        data = _minimal_manifest()
        m = AgentManifest.model_validate(data)
        assert m.identity.yanked_at is None
        assert m.identity.yanked_reason is None

    def test_yanked_fields_present(self):
        from agentversion.manifest import AgentManifest

        data = _minimal_manifest()
        data["identity"]["yanked_at"] = "2026-06-01T00:00:00Z"
        data["identity"]["yanked_reason"] = "CVE-2026-1234"
        m = AgentManifest.model_validate(data)
        assert m.identity.yanked_at is not None
        assert m.identity.yanked_reason == "CVE-2026-1234"

    def test_yanked_doesnt_change_hash(self):
        from agentversion.hasher import hash_manifest

        clean = _minimal_manifest()
        yanked = _minimal_manifest()
        yanked["identity"]["yanked_at"] = "2026-06-01T00:00:00Z"
        yanked["identity"]["yanked_reason"] = "CVE-2026-1234"
        # identity is not part of contract → hash unchanged
        assert hash_manifest(clean) == hash_manifest(yanked)
