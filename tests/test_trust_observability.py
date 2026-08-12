"""Tests for the 0.9.0 trust + observability + governance batch.

Covers §3d (attestation), §3m (richer ComparisonSummary), §3n (data classification).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _ts() -> str:
    return "2026-05-15T10:00:00Z"


def _minimal_manifest() -> dict:
    return {
        "spec_version": "0.9.0",
        "kind": "agent_manifest",
        "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
        "agent_name": "test",
        "version_label": "v1",
        "created_at": _ts(),
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


# ── §3d Attestation ───────────────────────────────────────


class TestAttestation:
    def test_model_basic(self):
        from agentversion.manifest import Attestation

        a = Attestation(
            signer="sigstore:github.com/decimalai/ci@main",
            algorithm="cosign-rsa-sha256",
            signature="MEUCIQDx9k",
            signed_payload_hash="sha256:47301b25",
            signed_at=datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
        )
        assert a.signer == "sigstore:github.com/decimalai/ci@main"
        assert a.key_id is None
        assert a.expires_at is None

    def test_attestations_default_empty(self):
        from agentversion.manifest import AgentManifest

        data = _minimal_manifest()
        m = AgentManifest.model_validate(data)
        assert m.identity.attestations == []

    def test_attestation_doesnt_affect_hash(self):
        """Attestations live on identity (not contract) → no hash change."""
        from agentversion.hasher import hash_manifest

        plain = _minimal_manifest()
        signed = _minimal_manifest()
        signed["identity"]["attestations"] = [
            {
                "signer": "sigstore:x",
                "algorithm": "cosign-rsa-sha256",
                "signature": "abc",
                "signed_payload_hash": "sha256:47301b25",
                "signed_at": _ts(),
            }
        ]
        assert hash_manifest(plain) == hash_manifest(signed)

    def test_multiple_attestations(self):
        from agentversion.manifest import AgentManifest

        data = _minimal_manifest()
        data["identity"]["attestations"] = [
            {
                "signer": "sigstore:ci",
                "algorithm": "cosign-rsa-sha256",
                "signature": "AAA",
                "signed_payload_hash": "sha256:h",
                "signed_at": _ts(),
            },
            {
                "signer": "user:release-manager",
                "algorithm": "ssh-ed25519",
                "signature": "BBB",
                "signed_payload_hash": "sha256:h",
                "signed_at": _ts(),
            },
        ]
        m = AgentManifest.model_validate(data)
        assert len(m.identity.attestations) == 2
        assert m.identity.attestations[0].algorithm == "cosign-rsa-sha256"
        assert m.identity.attestations[1].algorithm == "ssh-ed25519"

    def test_missing_required_field_rejected(self):
        from agentversion.manifest import AgentManifest

        data = _minimal_manifest()
        data["identity"]["attestations"] = [
            {"signer": "x", "algorithm": "y"}  # missing signature, signed_payload_hash, signed_at
        ]
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)


# ── §3m Richer ComparisonSummary ──────────────────────────


class TestComparisonSummaryRicher:
    def test_old_fields_still_supported(self):
        from agentversion.replay import ComparisonSummary

        cs = ComparisonSummary(
            final_output_changed=True,
            tool_path_changed=False,
            output_contract_valid=True,
        )
        assert cs.final_output_changed is True
        assert cs.final_output_diff_pct is None  # new field defaults to None

    def test_new_fields_present(self):
        from agentversion.replay import ComparisonSummary, ToolPathDiff

        cs = ComparisonSummary(
            final_output_changed=True,
            final_output_diff_pct=12.4,
            tool_path_changed=True,
            tool_path_diff=ToolPathDiff(
                steps_added=["validator_check"],
                steps_removed=[],
                first_divergence_step_index=3,
            ),
            step_count_delta=1,
            latency_delta_ms=850,
            cost_delta_usd=-0.003,
            eval_score_delta=-0.02,
        )
        assert cs.final_output_diff_pct == 12.4
        assert cs.tool_path_diff.first_divergence_step_index == 3
        assert cs.latency_delta_ms == 850
        assert cs.eval_score_delta == -0.02

    def test_diff_pct_range_enforced(self):
        from agentversion.replay import ComparisonSummary

        with pytest.raises(Exception):
            ComparisonSummary(final_output_diff_pct=150.0)
        with pytest.raises(Exception):
            ComparisonSummary(final_output_diff_pct=-1.0)

    def test_validates_against_schema(self):
        import json

        import jsonschema

        from agentversion.replay import (
            ComparisonSummary,
            ReplayResult,
            ToolPathDiff,
        )

        result = ReplayResult(
            replay_job_id="rpj_01HZK1A2B3C4D5E6F7G8H9J0K1",
            status="completed",
            target_manifest_id="amf_01HZK1A2B3C4D5E6F7G8H9J0K2",
            comparison_summary=ComparisonSummary(
                final_output_changed=True,
                final_output_diff_pct=8.2,
                tool_path_diff=ToolPathDiff(first_divergence_step_index=2),
                latency_delta_ms=-120,
            ),
        )
        schema = json.load(open("schemas/replay-result.schema.json"))
        jsonschema.validate(json.loads(result.model_dump_json()), schema)


# ── §3n Data classification ────────────────────────────────


class TestDataClassification:
    def test_default_pii_state(self):
        from agentversion.dataset import DataClassification

        dc = DataClassification()
        assert dc.pii_state == "none"
        assert dc.retention_days is None
        assert dc.residency == []
        assert dc.consent_basis is None

    def test_full(self):
        from agentversion.dataset import DataClassification

        dc = DataClassification(
            pii_state="redacted",
            retention_days=90,
            residency=["us-east-1", "eu-west-1"],
            redaction_policy_ref="redaction:v3.1",
            consent_basis="legitimate_interest",
        )
        assert dc.pii_state == "redacted"
        assert dc.consent_basis == "legitimate_interest"

    def test_invalid_pii_state(self):
        from agentversion.dataset import DataClassification

        with pytest.raises(Exception):
            DataClassification(pii_state="unredacted")  # type: ignore[arg-type]

    def test_invalid_consent_basis(self):
        from agentversion.dataset import DataClassification

        with pytest.raises(Exception):
            DataClassification(consent_basis="just_because")  # type: ignore[arg-type]

    def test_invalid_retention_days(self):
        from agentversion.dataset import DataClassification

        with pytest.raises(Exception):
            DataClassification(retention_days=0)
        with pytest.raises(Exception):
            DataClassification(retention_days=-1)

    def test_snapshot_with_classification(self):
        from agentversion.dataset import (
            DataClassification,
            DatasetSnapshot,
        )

        snap = DatasetSnapshot(
            snapshot_id="dss_01HZK1A2B3C4D5E6F7G8H9J0K1",
            name="finance_sft_2026_05",
            dataset_type="sft",
            created_at=datetime.now(timezone.utc),
            data_classification=DataClassification(
                pii_state="redacted",
                retention_days=180,
                residency=["us-east-1"],
            ),
        )
        assert snap.data_classification.pii_state == "redacted"

    def test_pii_state_filter_on_selection(self):
        from agentversion.dataset import DatasetSnapshot, SelectionPolicy

        snap = DatasetSnapshot(
            snapshot_id="dss_01HZK1A2B3C4D5E6F7G8H9J0K1",
            name="x",
            dataset_type="sft",
            created_at=datetime.now(timezone.utc),
            selection_policy=SelectionPolicy(
                pii_states=["redacted", "synthetic", "none"],
            ),
        )
        assert snap.selection_policy.pii_states == ["redacted", "synthetic", "none"]
        # "raw" not in the filter list

    def test_validates_against_schema(self):
        import json

        import jsonschema

        from agentversion.dataset import (
            DataClassification,
            DatasetSnapshot,
            SelectionPolicy,
        )

        snap = DatasetSnapshot(
            snapshot_id="dss_01HZK1A2B3C4D5E6F7G8H9J0K1",
            name="finance_sft",
            dataset_type="sft",
            created_at=datetime.now(timezone.utc),
            selection_policy=SelectionPolicy(pii_states=["redacted", "none"]),
            data_classification=DataClassification(
                pii_state="redacted",
                retention_days=90,
                residency=["us-east-1"],
                consent_basis="legitimate_interest",
            ),
        )
        schema = json.load(open("schemas/dataset-snapshot.schema.json"))
        jsonschema.validate(json.loads(snap.model_dump_json()), schema)
