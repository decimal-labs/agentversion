"""Tests for Pydantic manifest models."""

import json

import pytest

from agentversion.manifest import (
    AgentManifest,
    GenerationConfig,
    SubagentDescriptor,
)


def _minimal_manifest_data() -> dict:
    """Return minimal valid manifest as a dict."""
    return {
        "spec_version": "0.1.0",
        "kind": "agent_manifest",
        "manifest_id": "amf_test_001",
        "agent_name": "test-agent",
        "version_label": "v1",
        "created_at": "2026-03-10T10:00:00Z",
        "identity": {
            "overall_hash": "sha256:abc123",
        },
        "contract": {
            "prompt_stack": {
                "system_prompt": {
                    "id": "prompt_sys",
                    "version": "1",
                    "hash": "sha256:aaa",
                }
            },
            "model_runtime": {
                "provider": "google",
                "model": "gemini-2.0-flash",
            },
            "tool_registry": {
                "registry_version": "1",
                "registry_hash": "sha256:bbb",
                "tools": [
                    {
                        "name": "my_tool",
                        "version": "1",
                        "hash": "sha256:ccc",
                    }
                ],
            },
            "workflow": {
                "graph_name": "test-graph",
            },
            "output_contract": {
                "version": "1",
                "schema_hash": "sha256:ddd",
                "format": "text",
                "strict": False,
            },
        },
    }


class TestManifestParse:
    """Test parsing / deserialization."""

    def test_minimal_manifest(self):
        data = _minimal_manifest_data()
        m = AgentManifest.model_validate(data)
        assert m.agent_name == "test-agent"
        assert m.kind == "agent_manifest"
        assert m.spec_version == "0.1.0"

    def test_full_manifest_from_example(self):
        with open("examples/manifest/finance-agent-v1.json") as f:
            data = json.load(f)
        m = AgentManifest.model_validate(data)
        assert m.agent_name == "finance-agent"
        assert m.identity.hash_algorithm == "jcs-sha256"
        assert len(m.contract.tool_registry.tools) == 2

    def test_v2_example(self):
        with open("examples/manifest/finance-agent-v2.json") as f:
            data = json.load(f)
        m = AgentManifest.model_validate(data)
        assert len(m.contract.subagents) == 2
        assert m.contract.output_contract.strict is True
        assert m.contract.output_contract.format == "json"


class TestManifestSerialize:
    """Test serialization roundtrip."""

    def test_roundtrip(self):
        data = _minimal_manifest_data()
        m = AgentManifest.model_validate(data)
        output = json.loads(m.model_dump_json())
        m2 = AgentManifest.model_validate(output)
        assert m.manifest_id == m2.manifest_id
        assert m.identity.overall_hash == m2.identity.overall_hash

    def test_optional_fields_absent(self):
        data = _minimal_manifest_data()
        m = AgentManifest.model_validate(data)
        assert m.agent_namespace is None
        assert m.parent_manifest_id is None
        assert m.created_by is None
        assert m.contract.guardrails is None
        assert m.contract.context_config is None


class TestManifestValidation:
    """Test Pydantic validation catches bad data."""

    def test_missing_required_agent_name(self):
        data = _minimal_manifest_data()
        del data["agent_name"]
        with pytest.raises(Exception):  # ValidationError
            AgentManifest.model_validate(data)

    def test_missing_required_contract(self):
        data = _minimal_manifest_data()
        del data["contract"]
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)

    def test_missing_required_identity(self):
        data = _minimal_manifest_data()
        del data["identity"]
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)

    def test_invalid_kind(self):
        data = _minimal_manifest_data()
        data["kind"] = "wrong_kind"
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)

    def test_invalid_stability_enum(self):
        data = _minimal_manifest_data()
        data["contract"]["tool_registry"]["tools"][0]["stability"] = "invalid"
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)

    def test_invalid_reasoning_policy_enum(self):
        data = _minimal_manifest_data()
        data["contract"]["prompt_stack"]["reasoning_policy"] = "invalid"
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)


class TestGenerationConfig:
    """Test generation config model."""

    def test_parse(self):
        gc = GenerationConfig(temperature=0.5, top_p=0.9, max_tokens=2048)
        assert gc.temperature == 0.5
        assert gc.response_format is None

    def test_all_optional(self):
        gc = GenerationConfig()
        assert gc.temperature is None
        assert gc.top_p is None


class TestKindConsistency:
    """Verify that `kind` values across all spec objects are consistent.

    Design rule: `kind` values describe WHAT the object IS (e.g. "agent_manifest",
    "replay_job"), not which spec it belongs to. They should never contain the
    spec name (e.g. "agentversion").
    """

    SPEC_NAME_FRAGMENTS = ["agentversion", "agentversion", "version_spec"]

    def _get_all_kind_values(self) -> dict[str, str]:
        """Collect default kind values from all spec object models."""
        from agentversion.dataset import DatasetSnapshot, Episode, Step, Task
        from agentversion.decision import CompatibilityBatch, CompatibilityDecision
        from agentversion.manifest import AgentManifest
        from agentversion.replay import ReplayJob, ReplayResult

        models = {
            "AgentManifest": AgentManifest,
            "CompatibilityDecision": CompatibilityDecision,
            "CompatibilityBatch": CompatibilityBatch,
            "ReplayJob": ReplayJob,
            "ReplayResult": ReplayResult,
            "Task": Task,
            "Episode": Episode,
            "Step": Step,
            "DatasetSnapshot": DatasetSnapshot,
        }
        result = {}
        for name, model in models.items():
            fields = model.model_fields
            if "kind" in fields and fields["kind"].default is not None:
                result[name] = fields["kind"].default
        return result

    def test_kind_values_describe_object_type(self):
        """kind values should describe the object, not the spec name."""
        for model_name, kind_value in self._get_all_kind_values().items():
            for fragment in self.SPEC_NAME_FRAGMENTS:
                assert fragment not in kind_value, (
                    f"{model_name}.kind = '{kind_value}' contains spec name "
                    f"fragment '{fragment}'. kind should describe the object "
                    f"type (e.g. 'agent_manifest'), not the spec."
                )

    def test_kind_values_are_snake_case(self):
        """kind values should be lowercase snake_case."""
        import re
        for model_name, kind_value in self._get_all_kind_values().items():
            assert re.match(r"^[a-z][a-z0-9_]*$", kind_value), (
                f"{model_name}.kind = '{kind_value}' is not snake_case"
            )

    def test_example_manifests_have_correct_kind(self):
        """Example JSON files should have kind='agent_manifest'."""
        import glob
        for path in glob.glob("examples/manifest/*.json"):
            with open(path) as f:
                data = json.load(f)
            assert data.get("kind") == "agent_manifest", (
                f"{path} has kind='{data.get('kind')}', expected 'agent_manifest'"
            )


class TestSubagentManifestRef:
    """Test SubagentDescriptor.manifest_ref for recursive sub-agent support."""

    def test_subagent_with_manifest_ref(self):
        """A subagent can reference its own manifest via manifest_ref."""
        sd = SubagentDescriptor(
            name="billing-agent",
            version="2",
            hash="sha256:abc",
            manifest_ref="amf_billing_v2",
            handoff_schema_hash="sha256:def",
        )
        assert sd.manifest_ref == "amf_billing_v2"
        assert sd.name == "billing-agent"

    def test_subagent_without_manifest_ref(self):
        """manifest_ref is optional and defaults to None (backward compat)."""
        sd = SubagentDescriptor(
            name="simple-agent",
            version="1",
            hash="sha256:abc",
        )
        assert sd.manifest_ref is None
        assert sd.handoff_schema_hash is None

    def test_subagent_roundtrip(self):
        """SubagentDescriptor with manifest_ref survives JSON roundtrip."""
        sd = SubagentDescriptor(
            name="research-agent",
            version="3",
            hash="sha256:xyz",
            manifest_ref="amf_research_v3",
        )
        data = json.loads(sd.model_dump_json())
        sd2 = SubagentDescriptor.model_validate(data)
        assert sd2.manifest_ref == "amf_research_v3"
        assert sd2.name == "research-agent"

    def test_v2_example_has_manifest_ref(self):
        """finance-agent-v2.json should include manifest_ref on subagents."""
        with open("examples/manifest/finance-agent-v2.json") as f:
            data = json.load(f)
        m = AgentManifest.model_validate(data)
        for sa in m.contract.subagents:
            assert sa.manifest_ref is not None, (
                f"Subagent {sa.name} should have manifest_ref set"
            )

    def test_manifest_with_subagent_manifest_ref(self):
        """Full manifest parse should include subagent manifest_ref."""
        data = _minimal_manifest_data()
        data["contract"]["subagents"] = [
            {
                "name": "billing-agent",
                "version": "1",
                "hash": "sha256:aaa",
                "manifest_ref": "amf_billing_v1",
            },
            {
                "name": "tech-agent",
                "version": "1",
                "hash": "sha256:bbb",
            },
        ]
        m = AgentManifest.model_validate(data)
        assert len(m.contract.subagents) == 2
        assert m.contract.subagents[0].manifest_ref == "amf_billing_v1"
        assert m.contract.subagents[1].manifest_ref is None


class TestSkillRegistryModel:
    """Test SkillDescriptor and SkillRegistry Pydantic models."""

    def test_skill_descriptor_minimal(self):
        from agentversion.manifest import SkillDescriptor
        sd = SkillDescriptor(name="code-review", hash="sha256:abc")
        assert sd.name == "code-review"
        assert sd.version is None
        assert sd.stability is None
        assert sd.annotations is None

    def test_skill_descriptor_full(self):
        from agentversion.manifest import SkillDescriptor
        sd = SkillDescriptor(
            name="code-review",
            version="1.0",
            hash="sha256:abc",
            description="Reviews code for security and style",
            stability="stable",
            annotations={"author": "decimal-team"},
        )
        assert sd.version == "1.0"
        assert sd.stability == "stable"
        assert sd.description == "Reviews code for security and style"

    def test_skill_descriptor_invalid_stability(self):
        from agentversion.manifest import SkillDescriptor
        with pytest.raises(Exception):
            SkillDescriptor(name="x", hash="sha256:x", stability="invalid")

    def test_skill_registry_model(self):
        from agentversion.manifest import SkillDescriptor, SkillRegistry
        sr = SkillRegistry(
            registry_version="1",
            registry_hash="sha256:aaa",
            selection_strategy="llm_semantic",
            skills=[
                SkillDescriptor(name="code-review", hash="sha256:bbb"),
                SkillDescriptor(name="sql-optimizer", hash="sha256:ccc", stability="experimental"),
            ],
        )
        assert len(sr.skills) == 2
        assert sr.selection_strategy == "llm_semantic"

    def test_skill_registry_roundtrip(self):
        from agentversion.manifest import SkillDescriptor, SkillRegistry
        sr = SkillRegistry(
            registry_version="1",
            registry_hash="sha256:aaa",
            skills=[SkillDescriptor(name="code-review", hash="sha256:bbb")],
        )
        data = json.loads(sr.model_dump_json())
        sr2 = SkillRegistry.model_validate(data)
        assert sr2.skills[0].name == "code-review"
        assert sr2.registry_hash == "sha256:aaa"

    def test_manifest_with_skill_registry(self):
        """Full manifest with skill_registry parses correctly."""
        data = _minimal_manifest_data()
        data["contract"]["skill_registry"] = {
            "registry_version": "1",
            "registry_hash": "sha256:skill_reg",
            "selection_strategy": "llm_semantic",
            "skills": [
                {"name": "code-review", "hash": "sha256:cr", "version": "1.0", "stability": "stable"},
                {"name": "sql-optimizer", "hash": "sha256:sql", "stability": "experimental"},
            ],
        }
        m = AgentManifest.model_validate(data)
        assert m.contract.skill_registry is not None
        assert len(m.contract.skill_registry.skills) == 2
        assert m.contract.skill_registry.skills[0].name == "code-review"

    def test_manifest_without_skill_registry(self):
        """Existing manifests without skill_registry still parse (backward compat)."""
        data = _minimal_manifest_data()
        m = AgentManifest.model_validate(data)
        assert m.contract.skill_registry is None
