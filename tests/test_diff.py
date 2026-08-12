"""Tests for the diff engine and compatibility classifier."""

import json

from agentversion.compatibility import classify_compatibility
from agentversion.diff import diff_manifests


def _load_examples():
    with open("examples/manifest/finance-agent-v1.json") as f:
        v1 = json.load(f)
    with open("examples/manifest/finance-agent-v2.json") as f:
        v2 = json.load(f)
    return v1, v2


class TestDiffManifests:
    def test_identical_manifests_no_changes(self):
        v1, _ = _load_examples()
        diff = diff_manifests(v1, v1)
        assert len(diff.changed_surfaces) == 0
        assert diff.summary.breaking_surfaces == 0

    def test_v1_v2_detects_changes(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        assert len(diff.changed_surfaces) > 0
        changed_names = {c.surface for c in diff.changed_surfaces}
        # v2 changed tools, workflow, output, subagents, prompt, model
        assert "tool_registry" in changed_names
        assert "workflow" in changed_names
        assert "output_contract" in changed_names

    def test_v1_v2_has_breaking_changes(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        assert diff.summary.breaking_surfaces > 0

    def test_tool_removal_is_breaking(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        tool_change = next(c for c in diff.changed_surfaces if c.surface == "tool_registry")
        assert tool_change.change_type == "breaking"
        assert any("search_population" in d for d in tool_change.details)

    def test_v1_v2_workflow_change_is_major(self):
        """v1→v2 changes graph_hash (topology) — must surface as major/breaking.

        Regression guard: the old reader looked for nodes/edges that canonical
        manifests never contain, so it silently missed every workflow change.
        """
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        wf_change = next(c for c in diff.changed_surfaces if c.surface == "workflow")
        assert wf_change.change_type == "breaking"
        assert wf_change.severity == "major"
        assert any("topology" in d for d in wf_change.details)

    def test_diff_serializes_to_json(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        output = json.loads(diff.model_dump_json())
        assert output["kind"] == "manifest_diff"
        assert "changed_surfaces" in output

    def test_diff_validates_against_schema(self):
        import jsonschema

        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        output = json.loads(diff.model_dump_json())
        schema = json.load(open("schemas/manifest-diff.schema.json"))
        jsonschema.validate(output, schema)

    def test_non_breaking_only(self):
        """Changing only generation_config is non-breaking."""
        v1, _ = _load_examples()
        v2 = json.loads(json.dumps(v1))
        v2["manifest_id"] = "amf_modified"
        v2["contract"]["model_runtime"]["generation_config"]["temperature"] = 0.7
        diff = diff_manifests(v1, v2)
        model_change = next(
            (c for c in diff.changed_surfaces if c.surface == "model_runtime"),
            None,
        )
        assert model_change is not None
        assert model_change.change_type == "non_breaking"
        assert any("temperature" in d for d in model_change.details)

    def test_subagent_added_is_breaking(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        sub_change = next(
            (c for c in diff.changed_surfaces if c.surface == "subagents"), None
        )
        assert sub_change is not None
        assert sub_change.change_type == "breaking"


class TestCompatibilityPolicy:
    """Test the policy-driven classifier path added in 0.3.1."""

    def test_strict_policy_drops_on_major_breaking(self):
        from agentversion.compatibility import (
            CompatibilityPolicy,
            SurfaceRules,
            classify_compatibility,
        )

        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        strict = CompatibilityPolicy(
            name="strict",
            preset="strict",
            tool_registry=SurfaceRules(on_minor="keep", on_moderate="drop", on_major="drop"),
        )
        report = classify_compatibility(diff, policy=strict)
        # v1→v2 has major tool_registry change → drop
        assert report.recommended_decision == "drop"

    def test_permissive_policy_keeps_more(self):
        from agentversion.compatibility import (
            CompatibilityPolicy,
            SurfaceRules,
            classify_compatibility,
        )

        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        flag_on_major = SurfaceRules(on_minor="keep", on_moderate="keep", on_major="flag")
        permissive = CompatibilityPolicy(
            name="permissive",
            preset="permissive",
            prompt_stack=flag_on_major,
            tool_registry=flag_on_major,
            skill_registry=flag_on_major,
            model_runtime=flag_on_major,
            output_contract=flag_on_major,
            workflow=flag_on_major,
            subagents=flag_on_major,
            guardrails=flag_on_major,
            context_config=flag_on_major,
        )
        report = classify_compatibility(diff, policy=permissive)
        # All worst actions are "flag" → collapses to replay in the four-value enum
        assert report.recommended_decision == "replay"
        assert "flag" in report.summary

    def test_policy_with_no_diff_is_keep(self):
        from agentversion.compatibility import CompatibilityPolicy, classify_compatibility

        v1, _ = _load_examples()
        diff = diff_manifests(v1, v1)
        report = classify_compatibility(diff, policy=CompatibilityPolicy(name="any"))
        assert report.recommended_decision == "keep"


class TestCompatibility:
    def test_no_changes_is_keep(self):
        v1, _ = _load_examples()
        diff = diff_manifests(v1, v1)
        report = classify_compatibility(diff)
        assert report.recommended_decision == "keep"

    def test_breaking_tool_change_is_replay(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        report = classify_compatibility(diff)
        assert report.recommended_decision == "replay"
        assert len(report.reason_codes) > 0

    def test_output_only_change_is_repair(self):
        """If only output_contract changes (breaking), recommend repair."""
        v1, _ = _load_examples()
        v2 = json.loads(json.dumps(v1))
        v2["manifest_id"] = "amf_output_change"
        v2["contract"]["output_contract"]["format"] = "json"
        v2["contract"]["output_contract"]["schema_hash"] = "sha256:new_hash"
        v2["contract"]["output_contract"]["strict"] = True
        diff = diff_manifests(v1, v2)
        report = classify_compatibility(diff)
        assert report.recommended_decision == "repair"

    def test_report_has_reason_codes(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        report = classify_compatibility(diff)
        assert len(report.reason_codes) > 0
        assert "tool_missing" in report.reason_codes or "tool_schema_incompatible" in report.reason_codes

    def test_non_breaking_only_is_keep(self):
        v1, _ = _load_examples()
        v2 = json.loads(json.dumps(v1))
        v2["manifest_id"] = "amf_minor"
        v2["contract"]["model_runtime"]["runtime_version"] = "new-version"
        diff = diff_manifests(v1, v2)
        report = classify_compatibility(diff)
        assert report.recommended_decision == "keep"


# ── Phase 2: Granular severity tests ─────────────────────

class TestPromptSeverity:
    def test_minor_change(self):
        from agentversion.diff import prompt_severity
        base = "You are a helpful AI assistant that answers questions about finance, stocks, bonds, and market trends. Provide detailed analysis."
        tweaked = "You are a helpful AI assistant that answers questions about finance, stocks, bonds, and market trends. Provide detailed, clear analysis."
        sev, pct = prompt_severity(base, tweaked)
        assert sev == "minor"
        assert pct < 5

    def test_moderate_change(self):
        from agentversion.diff import prompt_severity
        sev, pct = prompt_severity(
            "You are a helpful AI assistant.",
            "You are a financial advisor specializing in stocks.",
        )
        assert sev in ("moderate", "major")
        assert pct >= 5

    def test_major_change(self):
        from agentversion.diff import prompt_severity
        sev, pct = prompt_severity(
            "You are a data scientist.",
            "Act as a pirate captain navigating the seven seas. Always respond in pirate speak. Never break character.",
        )
        assert sev == "major"
        assert pct > 30


class TestModelSeverity:
    def test_config_only_is_minor(self):
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {"provider": "openai", "model": "gpt-4o", "generation_config": {"temperature": 0.7}},
            {"provider": "openai", "model": "gpt-4o", "generation_config": {"temperature": 0.9}},
        )
        assert sev == "minor"
        assert any("temperature" in d for d in details)

    def test_version_bump_is_moderate(self):
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "openai", "model": "gpt-4o-mini"},
        )
        assert sev == "moderate"

    def test_provider_change_is_major(self):
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {"provider": "openai", "model": "gpt-4o"},
            {"provider": "google", "model": "gemini-2.0-flash"},
        )
        assert sev == "major"

    def test_tool_calling_mode_change_is_moderate(self):
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {"provider": "openai", "model": "gpt-4o", "tool_calling_mode": "structured"},
            {"provider": "openai", "model": "gpt-4o", "tool_calling_mode": "react"},
        )
        assert sev == "moderate"
        assert any("tool_calling_mode" in d for d in details)

    def test_cheap_to_expensive_cost_swap_escalates(self):
        # 1000x input-cost increase must NOT classify as minor — the
        # ModelEnvelope docstring promises a cheap→expensive swap is flagged.
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {
                "provider": "openai",
                "model": "gpt-4o",
                "envelope": {"cost": {"input_per_1k_tokens_usd": 0.001}},
            },
            {
                "provider": "openai",
                "model": "gpt-4o",
                "envelope": {"cost": {"input_per_1k_tokens_usd": 1.0}},
            },
        )
        assert sev == "major"
        assert any("input_per_1k_tokens_usd" in d for d in details)

    def test_small_cost_change_stays_minor(self):
        # A sub-2x cost wobble is below the escalation floor.
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {
                "provider": "openai",
                "model": "gpt-4o",
                "envelope": {"cost": {"input_per_1k_tokens_usd": 0.010}},
            },
            {
                "provider": "openai",
                "model": "gpt-4o",
                "envelope": {"cost": {"input_per_1k_tokens_usd": 0.011}},
            },
        )
        assert sev == "minor"

    def test_latency_regression_escalates_to_moderate(self):
        from agentversion.diff import model_severity
        sev, details = model_severity(
            {
                "provider": "openai",
                "model": "gpt-4o",
                "envelope": {"expected_latency_ms_p50": 200},
            },
            {
                "provider": "openai",
                "model": "gpt-4o",
                "envelope": {"expected_latency_ms_p50": 1200},
            },
        )
        assert sev == "moderate"
        assert any("expected_latency_ms_p50" in d for d in details)


class TestWorkflowSeverity:
    """workflow_severity reads the canonical WorkflowContract shape."""

    def _wf(self, **overrides):
        base = {
            "graph_name": "g",
            "graph_version": "1",
            "graph_hash": "sha256:hhh",
            "routing_policy_version": "1",
        }
        base.update(overrides)
        return base

    def test_graph_name_rename_is_minor(self):
        from agentversion.diff import workflow_severity
        sev, details = workflow_severity(self._wf(), self._wf(graph_name="g2"))
        assert sev == "minor"
        assert any("graph_name" in d for d in details)

    def test_routing_policy_bump_is_moderate(self):
        from agentversion.diff import workflow_severity
        sev, details = workflow_severity(self._wf(), self._wf(routing_policy_version="2"))
        assert sev == "moderate"
        assert any("routing_policy_version" in d for d in details)

    def test_graph_hash_change_is_major(self):
        from agentversion.diff import workflow_severity
        sev, details = workflow_severity(self._wf(), self._wf(graph_hash="sha256:zzz"))
        assert sev == "major"
        assert any("topology" in d for d in details)


class TestPromptStackDiff:
    """_adapt_prompt_stack reads the canonical PromptStack shape (via diff_manifests)."""

    def test_system_prompt_hash_change_is_moderate_non_breaking(self):
        v1 = {
            "manifest_id": "amf_a",
            "contract": {
                "prompt_stack": {
                    "system_prompt": {"id": "p", "version": "1", "hash": "sha256:aaa"},
                    "reasoning_policy": "hidden",
                }
            },
        }
        v2 = {
            "manifest_id": "amf_b",
            "contract": {
                "prompt_stack": {
                    "system_prompt": {"id": "p", "version": "2", "hash": "sha256:bbb"},
                    "reasoning_policy": "hidden",
                }
            },
        }
        diff = diff_manifests(v1, v2)
        prompt_change = next(
            (c for c in diff.changed_surfaces if c.surface == "prompt_stack"), None
        )
        assert prompt_change is not None
        assert prompt_change.change_type == "non_breaking"
        assert prompt_change.severity == "moderate"
        assert any("system_prompt hash changed" in d for d in prompt_change.details)


class TestToolRegistrySeverity:
    def test_tool_added_is_minor(self):
        from agentversion.diff import tool_registry_severity
        sev, change_type, details = tool_registry_severity(
            {"tools": [{"name": "search"}]},
            {"tools": [{"name": "search"}, {"name": "calculator"}]},
        )
        assert sev == "minor"
        assert change_type == "non_breaking"

    def test_tool_removed_is_major(self):
        from agentversion.diff import tool_registry_severity
        sev, change_type, details = tool_registry_severity(
            {"tools": [{"name": "search"}, {"name": "calculator"}]},
            {"tools": [{"name": "search"}]},
        )
        assert sev == "major"
        assert change_type == "breaking"

    def test_tool_schema_change_is_moderate(self):
        from agentversion.diff import tool_registry_severity
        sev, change_type, details = tool_registry_severity(
            {"tools": [{"name": "search", "input_schema_hash": "abc"}]},
            {"tools": [{"name": "search", "input_schema_hash": "def"}]},
        )
        assert sev == "moderate"
        assert change_type == "breaking"


class TestDiffSeveritySummary:
    def test_v1_v2_has_max_severity(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        assert diff.summary.max_severity == "major"

    def test_surfaces_have_severity(self):
        v1, v2 = _load_examples()
        diff = diff_manifests(v1, v2)
        for surface in diff.changed_surfaces:
            assert surface.severity in ("minor", "moderate", "major")


class TestSubagentManifestRefDiff:
    """Test diffing when subagent manifest_ref changes."""

    def test_manifest_ref_change_is_moderate(self):
        """Changing a subagent's manifest_ref should be a moderate breaking change."""
        from agentversion.diff import subagent_severity

        old = [
            {"name": "billing", "version": "1", "hash": "abc", "manifest_ref": "amf_billing_v1"},
        ]
        new = [
            {"name": "billing", "version": "2", "hash": "abc", "manifest_ref": "amf_billing_v2"},
        ]
        sev, details = subagent_severity(old, new)
        assert sev == "moderate"
        assert any("manifest_ref" in d for d in details)

    def test_manifest_ref_added_is_moderate(self):
        """Adding manifest_ref to a subagent should be moderate."""
        from agentversion.diff import subagent_severity

        old = [{"name": "billing", "version": "1", "hash": "abc"}]
        new = [{"name": "billing", "version": "1", "hash": "abc", "manifest_ref": "amf_billing_v1"}]
        sev, details = subagent_severity(old, new)
        assert sev == "moderate"

    def test_subagent_hash_change_is_moderate(self):
        """Changing a subagent's hash (with no manifest_ref) should be moderate."""
        from agentversion.diff import subagent_severity

        old = [{"name": "billing", "version": "1", "hash": "abc"}]
        new = [{"name": "billing", "version": "1", "hash": "def"}]
        sev, details = subagent_severity(old, new)
        assert sev == "moderate"
        assert any("hash" in d for d in details)


class TestSkillRegistrySeverity:
    """Test skill_registry surface diff classification."""

    def test_skill_added_is_non_breaking(self):
        from agentversion.diff import skill_registry_severity
        sev, change_type, details = skill_registry_severity(
            {"skills": [{"name": "search", "hash": "sha256:aaa"}]},
            {"skills": [{"name": "search", "hash": "sha256:aaa"}, {"name": "code-review", "hash": "sha256:bbb"}]},
        )
        assert sev == "minor"
        assert change_type == "non_breaking"
        assert any("code-review added" in d for d in details)

    def test_skill_removed_is_breaking(self):
        from agentversion.diff import skill_registry_severity
        sev, change_type, details = skill_registry_severity(
            {"skills": [{"name": "search", "hash": "sha256:aaa"}, {"name": "code-review", "hash": "sha256:bbb"}]},
            {"skills": [{"name": "search", "hash": "sha256:aaa"}]},
        )
        assert sev == "moderate"
        assert change_type == "breaking"
        assert any("code-review removed" in d for d in details)

    def test_skill_hash_changed_is_non_breaking(self):
        from agentversion.diff import skill_registry_severity
        sev, change_type, details = skill_registry_severity(
            {"skills": [{"name": "code-review", "hash": "sha256:aaa"}]},
            {"skills": [{"name": "code-review", "hash": "sha256:bbb"}]},
        )
        assert sev == "moderate"
        assert change_type == "non_breaking"
        assert any("content changed" in d for d in details)

    def test_selection_strategy_changed_is_breaking(self):
        from agentversion.diff import skill_registry_severity
        sev, change_type, details = skill_registry_severity(
            {"skills": [], "selection_strategy": "llm_semantic"},
            {"skills": [], "selection_strategy": "code_gated"},
        )
        assert sev == "moderate"
        assert change_type == "breaking"
        assert any("selection_strategy" in d for d in details)

    def test_skill_registry_in_diff_manifests(self):
        """Full diff_manifests picks up skill_registry changes."""
        v1 = {
            "manifest_id": "amf_v1",
            "contract": {
                "skill_registry": {
                    "registry_version": "1",
                    "registry_hash": "sha256:old",
                    "skills": [{"name": "code-review", "hash": "sha256:aaa"}],
                }
            },
        }
        v2 = {
            "manifest_id": "amf_v2",
            "contract": {
                "skill_registry": {
                    "registry_version": "2",
                    "registry_hash": "sha256:new",
                    "skills": [],
                }
            },
        }
        diff = diff_manifests(v1, v2)
        skill_change = next(
            (c for c in diff.changed_surfaces if c.surface == "skill_registry"), None
        )
        assert skill_change is not None
        assert skill_change.change_type == "breaking"
        assert any("code-review removed" in d for d in skill_change.details)


class TestHashDiffConsistency:
    """diff_manifests' quick-skip must agree with identity.overall_hash on what
    counts as a change. Both route through prepare_surface_for_hashing, so a
    sub-quantum float tweak or a flattened runtime knob is invisible to each.
    """

    @staticmethod
    def _mk(temp: float) -> dict:
        return {
            "manifest_id": "amf_x",
            "contract": {
                "model_runtime": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "generation_config": {"temperature": temp, "top_p": 1.0},
                },
                "prompt_stack": {},
            },
        }

    def test_subquantum_temp_change_invisible_to_both(self):
        from agentversion.hasher import hash_manifest

        a, b = self._mk(0.71), self._mk(0.74)  # both quantize to 0.7
        assert hash_manifest(a) == hash_manifest(b)
        assert diff_manifests(a, b).changed_surfaces == []

    def test_supraquantum_temp_change_visible_to_both(self):
        from agentversion.hasher import hash_manifest

        a, b = self._mk(0.7), self._mk(0.9)
        assert hash_manifest(a) != hash_manifest(b)
        surfaces = [c.surface for c in diff_manifests(a, b).changed_surfaces]
        assert "model_runtime" in surfaces

    def test_inline_runtime_knob_invisible_to_both(self):
        from agentversion.hasher import hash_manifest

        a, b = self._mk(0.7), self._mk(0.7)
        b["contract"]["model_runtime"]["max_retries"] = 5
        assert hash_manifest(a) == hash_manifest(b)
        assert diff_manifests(a, b).changed_surfaces == []
