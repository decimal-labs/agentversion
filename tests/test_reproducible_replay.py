"""Tests for the reproducible-replay batch (§3f, §3g, §3h, §3i), added in v0.8.0.

These features work together to make replays bit-reproducible:
- §3i tool semantic_version: catches behavioral drift schemas miss
- §3g tool schema embedding: makes tool schemas portable / offline-replayable
- §3h model cost envelope: anchors ReplayConstraints budgeting
- §3f determinism hints: pins seed / clock / tool responses
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentversion.hasher import hash_surface


def _ts() -> str:
    return "2026-05-12T10:00:00Z"


# ── §3i Tool semantic_version ──────────────────────────


class TestToolSemanticVersion:
    def test_field_present_on_descriptor(self):
        from agentversion.manifest import ToolDescriptor

        t = ToolDescriptor(
            name="search",
            hash="sha256:abc",
            semantic_version="1.4.2",
            implementation_ref="git:abcdef@scripts/tools/search.py",
        )
        assert t.semantic_version == "1.4.2"
        assert t.implementation_ref == "git:abcdef@scripts/tools/search.py"

    def test_validator_flags_malformed_semver(self):
        from agentversion.validator import validate_manifest

        data = _minimal_manifest()
        data["contract"]["tool_registry"]["tools"].append({
            "name": "search", "hash": "sha256:abc",
            "semantic_version": "not.a.semver",
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.warnings}
        assert "malformed_semver" in codes

    def test_diff_picks_up_major_bump_as_breaking(self):
        from agentversion.diff import tool_registry_severity

        old = {"tools": [{
            "name": "search", "hash": "sha256:abc",
            "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o",
            "semantic_version": "1.4.2",
        }]}
        new = {"tools": [{
            "name": "search", "hash": "sha256:abc",
            "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o",
            "semantic_version": "2.0.0",
        }]}
        sev, change_type, details = tool_registry_severity(old, new)
        assert change_type == "breaking"
        assert sev == "moderate"
        assert any("major bump" in d for d in details)

    def test_diff_minor_bump_is_non_breaking_minor(self):
        from agentversion.diff import tool_registry_severity

        old = {"tools": [{
            "name": "search", "hash": "sha256:abc",
            "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o",
            "semantic_version": "1.4.2",
        }]}
        new = {"tools": [{
            "name": "search", "hash": "sha256:abc",
            "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o",
            "semantic_version": "1.5.0",
        }]}
        sev, change_type, details = tool_registry_severity(old, new)
        assert change_type == "non_breaking"
        assert sev == "minor"
        assert any("minor bump" in d for d in details)

    def test_diff_patch_bump_is_minor(self):
        from agentversion.diff import tool_registry_severity

        old = {"tools": [{
            "name": "search", "hash": "sha256:abc",
            "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o",
            "semantic_version": "1.4.2",
        }]}
        new = {"tools": [{
            "name": "search", "hash": "sha256:abc",
            "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o",
            "semantic_version": "1.4.3",
        }]}
        sev, change_type, details = tool_registry_severity(old, new)
        assert change_type == "non_breaking"
        assert sev == "minor"


# ── §3g Tool schema embedding ─────────────────────────────


class TestToolSchemaEmbedding:
    def test_inline_fields_optional(self):
        from agentversion.manifest import ToolDescriptor

        t = ToolDescriptor(name="x", hash="sha256:a")
        assert t.input_schema_inline is None
        assert t.output_schema_inline is None

    def test_inline_hash_equivalence_passes(self):
        from agentversion.validator import validate_manifest

        schema = {"type": "object", "properties": {"ticker": {"type": "string"}}}
        h = hash_surface(schema)

        data = _minimal_manifest()
        data["contract"]["tool_registry"]["tools"].append({
            "name": "get_market_cap",
            "hash": "sha256:abc",
            "input_schema_hash": h,
            "input_schema_inline": schema,
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "schema_hash_mismatch" not in codes

    def test_inline_hash_mismatch_is_error(self):
        from agentversion.validator import validate_manifest

        data = _minimal_manifest()
        data["contract"]["tool_registry"]["tools"].append({
            "name": "get_market_cap",
            "hash": "sha256:abc",
            "input_schema_hash": "sha256:wrong",  # wrong hash for the inline schema
            "input_schema_inline": {"type": "object"},
        })
        result = validate_manifest(data, check_hash=False)
        assert result.valid is False
        codes = {i.code for i in result.errors}
        assert "schema_hash_mismatch" in codes

    def test_inline_without_declared_hash_is_fine(self):
        """If you supply only inline (no declared hash), there's nothing to mismatch against."""
        from agentversion.validator import validate_manifest

        data = _minimal_manifest()
        data["contract"]["tool_registry"]["tools"].append({
            "name": "x",
            "hash": "sha256:abc",
            "input_schema_inline": {"type": "object"},
        })
        result = validate_manifest(data, check_hash=False)
        codes = {i.code for i in result.issues}
        assert "schema_hash_mismatch" not in codes


# ── §3h Cost & limits envelope ────────────────────────────


class TestCostEnvelope:
    def test_envelope_field_present(self):
        from agentversion.manifest import (
            CostEnvelope,
            ModelEnvelope,
            ModelRuntime,
            RateLimit,
        )

        mr = ModelRuntime(
            provider="openai",
            model="gpt-4o",
            envelope=ModelEnvelope(
                context_window_tokens=128000,
                expected_latency_ms_p50=1200,
                expected_latency_ms_p99=8000,
                cost=CostEnvelope(
                    input_per_1k_tokens_usd=0.0025,
                    output_per_1k_tokens_usd=0.01,
                ),
                rate_limit=RateLimit(rpm=500, tpm=800000),
            ),
        )
        assert mr.envelope.context_window_tokens == 128000
        assert mr.envelope.cost.output_per_1k_tokens_usd == 0.01

    def test_envelope_participates_in_hash(self):
        """Envelope is part of model_runtime, which is in contract → affects overall_hash."""
        from agentversion.hasher import hash_manifest

        m1 = _minimal_manifest()
        m1["contract"]["model_runtime"]["envelope"] = {
            "cost": {"input_per_1k_tokens_usd": 0.0025}
        }

        m2 = _minimal_manifest()
        m2["contract"]["model_runtime"]["envelope"] = {
            "cost": {"input_per_1k_tokens_usd": 0.015}  # more expensive
        }

        assert hash_manifest(m1) != hash_manifest(m2)

    def test_envelope_diff_via_full_manifest(self):
        """A pricing bump should show up as a model_runtime change in the diff."""
        from agentversion.diff import diff_manifests

        v1 = _minimal_manifest()
        v1["manifest_id"] = "amf_01HZK1A2B3C4D5E6F7G8H9J0K1"
        v1["contract"]["model_runtime"]["envelope"] = {
            "cost": {"input_per_1k_tokens_usd": 0.0025}
        }

        v2 = _minimal_manifest()
        v2["manifest_id"] = "amf_01HZK1A2B3C4D5E6F7G8H9J0K2"
        v2["contract"]["model_runtime"]["envelope"] = {
            "cost": {"input_per_1k_tokens_usd": 0.015}
        }

        diff = diff_manifests(v1, v2)
        surfaces = {c.surface for c in diff.changed_surfaces}
        assert "model_runtime" in surfaces


# ── §3f Determinism hints on ReplayJob ─────────────────────


class TestDeterminismHints:
    def test_field_on_replay_input(self):
        from agentversion.replay import (
            DeterminismHints,
            Message,
            ReplayInput,
            ReplayJob,
        )

        job = ReplayJob(
            replay_job_id="rpj_01HZK1A2B3C4D5E6F7G8H9J0K1",
            task_id="tsk_01HZK1A2B3C4D5E6F7G8H9J0K2",
            target_manifest_id="amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
            mode="offline_batch",
            priority="normal",
            replay_input=ReplayInput(
                messages=[Message(role="user", content="hi")],
                determinism=DeterminismHints(
                    random_seed=12345,
                    clock_freeze_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
                    tool_response_pinning_ref="agentversion:hash:sha256:abcdef",
                ),
            ),
            created_at=datetime.now(timezone.utc),
        )
        assert job.replay_input.determinism.random_seed == 12345
        assert job.replay_input.determinism.clock_freeze_at.year == 2026

    def test_determinism_validates_against_schema(self):
        import json

        import jsonschema

        from agentversion.replay import (
            DeterminismHints,
            Message,
            ReplayInput,
            ReplayJob,
        )

        job = ReplayJob(
            replay_job_id="rpj_01HZK1A2B3C4D5E6F7G8H9J0K1",
            task_id="tsk_01HZK1A2B3C4D5E6F7G8H9J0K2",
            target_manifest_id="amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
            mode="customer_runtime",
            priority="normal",
            replay_input=ReplayInput(
                messages=[Message(role="user", content="hi")],
                determinism=DeterminismHints(random_seed=42),
            ),
            created_at=datetime.now(timezone.utc),
        )
        schema = json.load(open("schemas/replay-job.schema.json"))
        jsonschema.validate(json.loads(job.model_dump_json()), schema)


# ── Helpers ────────────────────────────────────────────────


def _minimal_manifest() -> dict:
    return {
        "spec_version": "0.8.0",
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
