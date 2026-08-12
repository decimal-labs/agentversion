"""Tests for the environment surface (§3a, added in v0.6.0)."""

from __future__ import annotations

# ── Model parsing ───────────────────────────────────────


class TestEnvironmentModel:
    def test_empty(self):
        from agentversion.manifest import Environment

        e = Environment()
        assert e.deployment_id is None
        assert e.region is None
        assert e.runtime_versions == {}
        assert e.secret_refs == []
        assert e.external_service_pins == {}
        assert e.feature_flags == {}
        assert e.resource_limits is None

    def test_full(self):
        from agentversion.manifest import Environment, ResourceLimits

        e = Environment(
            deployment_id="prod-east-1",
            region="us-east-1",
            infra_image_hash="sha256:abc",
            runtime_versions={"python": "3.12.5"},
            secret_refs=["prod/openai-key"],
            external_service_pins={"openai": "v1@2024-10-01"},
            feature_flags={"new_router": True},
            resource_limits=ResourceLimits(memory_mb=2048, timeout_seconds=120),
        )
        assert e.region == "us-east-1"
        assert e.resource_limits.memory_mb == 2048

    def test_roundtrip(self):
        from agentversion.manifest import Environment, ResourceLimits

        e = Environment(
            region="us-east-1",
            resource_limits=ResourceLimits(memory_mb=1024),
        )
        import json
        d = json.loads(e.model_dump_json())
        e2 = Environment.model_validate(d)
        assert e2.region == "us-east-1"
        assert e2.resource_limits.memory_mb == 1024


# ── Hash inclusion ──────────────────────────────────────


class TestEnvironmentHashing:
    def _manifest_with_env(self, **env_overrides) -> dict:
        env = {
            "deployment_id": "prod",
            "region": "us-east-1",
            **env_overrides,
        }
        return {
            "contract": {
                "prompt_stack": {"reasoning_policy": "hidden"},
                "model_runtime": {"provider": "openai", "model": "gpt-4o"},
                "tool_registry": {
                    "registry_version": "1",
                    "registry_hash": "sha256:r",
                    "tools": [],
                },
                "workflow": {"graph_name": "g"},
                "output_contract": {
                    "version": "1", "schema_hash": "sha256:o",
                    "format": "text", "strict": False,
                },
                "environment": env,
            }
        }

    def test_env_change_affects_overall_hash(self):
        from agentversion.hasher import hash_manifest

        h1 = hash_manifest(self._manifest_with_env(region="us-east-1"))
        h2 = hash_manifest(self._manifest_with_env(region="us-west-2"))
        assert h1 != h2

    def test_no_env_block_vs_with_env_differs(self):
        from agentversion.hasher import hash_manifest

        base = self._manifest_with_env()
        no_env = {"contract": {k: v for k, v in base["contract"].items() if k != "environment"}}
        assert hash_manifest(base) != hash_manifest(no_env)


# ── Diff severity ────────────────────────────────────────


class TestEnvironmentSeverity:
    def test_no_change_is_minor(self):
        from agentversion.diff import environment_severity

        sev, details = environment_severity({"region": "us-east-1"}, {"region": "us-east-1"})
        assert sev == "minor"

    def test_deployment_id_change_is_minor(self):
        from agentversion.diff import environment_severity

        sev, details = environment_severity(
            {"deployment_id": "prod-east-1"},
            {"deployment_id": "prod-east-1-v2"},
        )
        assert sev == "minor"
        assert any("deployment_id" in d for d in details)

    def test_region_change_is_moderate(self):
        from agentversion.diff import environment_severity

        sev, details = environment_severity({"region": "us-east-1"}, {"region": "us-west-2"})
        assert sev == "moderate"

    def test_infra_image_change_is_moderate(self):
        from agentversion.diff import environment_severity

        sev, _ = environment_severity(
            {"infra_image_hash": "sha256:aaa"},
            {"infra_image_hash": "sha256:bbb"},
        )
        assert sev == "moderate"

    def test_runtime_versions_change_is_moderate(self):
        from agentversion.diff import environment_severity

        sev, details = environment_severity(
            {"runtime_versions": {"python": "3.10.0"}},
            {"runtime_versions": {"python": "3.12.5"}},
        )
        assert sev == "moderate"
        assert any("runtime_versions" in d for d in details)

    def test_external_service_pins_change_is_moderate(self):
        from agentversion.diff import environment_severity

        sev, _ = environment_severity(
            {"external_service_pins": {"openai": "v1@2024-10-01"}},
            {"external_service_pins": {"openai": "v1@2024-12-15"}},
        )
        assert sev == "moderate"

    def test_secret_refs_change_is_minor(self):
        from agentversion.diff import environment_severity

        sev, _ = environment_severity(
            {"secret_refs": ["prod/old-key"]},
            {"secret_refs": ["prod/new-key"]},
        )
        assert sev == "minor"

    def test_resource_limits_change_is_minor(self):
        from agentversion.diff import environment_severity

        sev, _ = environment_severity(
            {"resource_limits": {"memory_mb": 1024}},
            {"resource_limits": {"memory_mb": 2048}},
        )
        assert sev == "minor"


# ── End-to-end diff ──────────────────────────────────────


class TestEnvironmentDiffIntegration:
    def _base(self) -> dict:
        return {
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "openai", "model": "gpt-4o"},
                "tool_registry": {"registry_version": "1", "registry_hash": "r", "tools": []},
                "workflow": {"graph_name": "g"},
                "output_contract": {"version": "1", "schema_hash": "o",
                                    "format": "text", "strict": False},
                "environment": {
                    "deployment_id": "prod",
                    "region": "us-east-1",
                    "infra_image_hash": "sha256:abc",
                },
            },
        }

    def test_diff_picks_up_environment_changes(self):
        from agentversion.diff import diff_manifests

        v1 = self._base()
        v2 = self._base()
        v2["manifest_id"] = "amf_01HZK1A2B3C4D5E6F7G8H9J0K2"
        v2["contract"]["environment"]["region"] = "us-west-2"

        diff = diff_manifests(v1, v2)
        env_changes = [c for c in diff.changed_surfaces if c.surface == "environment"]
        assert len(env_changes) == 1
        assert env_changes[0].change_type == "non_breaking"  # env changes don't invalidate past data
        assert env_changes[0].severity == "moderate"

    def test_environment_in_compatibility_report(self):
        from agentversion.compatibility import classify_compatibility
        from agentversion.diff import diff_manifests

        v1 = self._base()
        v2 = self._base()
        v2["manifest_id"] = "amf_01HZK1A2B3C4D5E6F7G8H9J0K2"
        v2["contract"]["environment"]["infra_image_hash"] = "sha256:def"

        diff = diff_manifests(v1, v2)
        report = classify_compatibility(diff)
        # Only env changed (non-breaking) → keep
        assert report.recommended_decision == "keep"
        # But reason codes include env-specific reasons
        assert any(
            code in report.reason_codes
            for code in [
                "region_changed", "infra_image_changed",
                "external_service_pin_changed", "runtime_version_changed",
            ]
        )


# ── Policy integration ───────────────────────────────────


class TestEnvironmentPolicy:
    def test_policy_can_drop_on_env_change(self):
        from agentversion.compatibility import (
            CompatibilityPolicy,
            SurfaceRules,
            classify_compatibility,
        )
        from agentversion.diff import diff_manifests

        v1 = {
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "openai", "model": "gpt-4o"},
                "tool_registry": {"registry_version": "1", "registry_hash": "r", "tools": []},
                "workflow": {"graph_name": "g"},
                "output_contract": {"version": "1", "schema_hash": "o",
                                    "format": "text", "strict": False},
                "environment": {"region": "us-east-1"},
            },
        }
        v2 = {
            **v1,
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K2",
            "contract": {**v1["contract"], "environment": {"region": "us-west-2"}},
        }

        diff = diff_manifests(v1, v2)
        # Strict policy: drop on moderate environment changes
        strict = CompatibilityPolicy(
            name="strict",
            environment=SurfaceRules(on_minor="keep", on_moderate="drop", on_major="drop"),
        )
        report = classify_compatibility(diff, policy=strict)
        assert report.recommended_decision == "drop"


# ── Condition DSL ────────────────────────────────────────


class TestEnvironmentConditionTokens:
    def test_environment_tokens_are_registered(self):
        from agentversion.decision import SURFACE_STATE_TOKENS

        assert "environment_surface_changed" in SURFACE_STATE_TOKENS
        assert "environment_surface_unchanged" in SURFACE_STATE_TOKENS

    def test_classification_rule_accepts_environment_token(self):
        from agentversion.decision import ClassificationRule

        rule = ClassificationRule(
            rule_id="env_strict",
            condition="environment_surface_changed",
            decision="drop",
            reason_codes=["region_changed"],
            matched_count=42,
        )
        assert rule.condition == "environment_surface_changed"

    def test_new_reason_codes_in_enum(self):
        from agentversion.decision import REASON_CODES

        assert "region_changed" in REASON_CODES
        assert "infra_image_changed" in REASON_CODES
        assert "external_service_pin_changed" in REASON_CODES
        assert "runtime_version_changed" in REASON_CODES
