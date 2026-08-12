"""Tests for AgentVersion v0.2.0 audit changes.

Covers: quantized float hashing, new manifest fields (status, capabilities,
modalities, tool description/annotations), tool version optional, condition
DSL validation, and new JSON schemas.
"""

import json

import pytest

from agentversion.decision import (
    ClassificationRule,
    validate_condition,
)
from agentversion.hasher import (
    _quantize_generation_config,
    hash_manifest,
    quantize_float,
)
from agentversion.manifest import (
    AgentManifest,
    GenerationConfig,
    OutputContract,
    ToolDescriptor,
)

# ── Quantized Float Hashing ─────────────────────────────────────


class TestQuantizeFloat:
    """Test the quantize_float function (v0.2.0)."""

    def test_exact_step_unchanged(self):
        assert quantize_float(0.7, 0.1) == 0.7
        assert quantize_float(0.0, 0.1) == 0.0
        assert quantize_float(1.0, 0.1) == 1.0

    def test_rounds_to_nearest_step(self):
        assert quantize_float(0.71, 0.1) == 0.7
        assert quantize_float(0.75, 0.1) == 0.8
        assert quantize_float(0.74, 0.1) == 0.7

    def test_top_p_quantization(self):
        assert quantize_float(0.92, 0.05) == 0.90
        assert quantize_float(0.95, 0.05) == 0.95
        assert quantize_float(0.97, 0.05) == 0.95

    def test_none_returns_none(self):
        assert quantize_float(None, 0.1) is None

    def test_no_floating_point_artifacts(self):
        """Verify we don't get 0.7000000000000001."""
        result = quantize_float(0.71, 0.1)
        assert str(result) == "0.7"
        result = quantize_float(0.3, 0.1)
        assert str(result) == "0.3"


class TestQuantizeGenerationConfig:
    """Test generation_config quantization for hashing."""

    def test_quantizes_temperature(self):
        config = {"temperature": 0.71, "top_p": 1.0, "max_tokens": 4096}
        result = _quantize_generation_config(config)
        assert result["temperature"] == 0.7
        assert result["top_p"] == 1.0
        assert result["max_tokens"] == 4096

    def test_strips_runtime_only_keys(self):
        config = {"temperature": 0.5, "max_retries": 3, "timeout": 30}
        result = _quantize_generation_config(config)
        assert "max_retries" not in result
        assert "timeout" not in result
        assert result["temperature"] == 0.5

    def test_preserves_non_numeric_fields(self):
        config = {"temperature": 0.5, "response_format": "json_object"}
        result = _quantize_generation_config(config)
        assert result["response_format"] == "json_object"


class TestQuantizedManifestHashing:
    """Test that quantized hashing produces expected behavior."""

    def _make_manifest(self, temperature: float) -> dict:
        return {
            "contract": {
                "model_runtime": {
                    "provider": "google",
                    "model": "gemini-2.0-flash",
                    "generation_config": {
                        "temperature": temperature,
                        "top_p": 1.0,
                    },
                },
                "prompt_stack": {},
            }
        }

    def test_similar_temps_same_hash(self):
        """0.71 and 0.74 should both quantize to 0.7 → same hash."""
        h1 = hash_manifest(self._make_manifest(0.71))
        h2 = hash_manifest(self._make_manifest(0.74))
        assert h1 == h2

    def test_different_temps_different_hash(self):
        """0.7 and 0.8 should produce different hashes."""
        h1 = hash_manifest(self._make_manifest(0.7))
        h2 = hash_manifest(self._make_manifest(0.8))
        assert h1 != h2

    def test_exact_zero_unchanged(self):
        """temperature=0.0 should hash the same as temperature=0.0."""
        h1 = hash_manifest(self._make_manifest(0.0))
        h2 = hash_manifest(self._make_manifest(0.0))
        assert h1 == h2

    def test_runtime_only_keys_excluded(self):
        """max_retries shouldn't affect the hash."""
        m1 = self._make_manifest(0.5)
        m2 = self._make_manifest(0.5)
        m2["contract"]["model_runtime"]["max_retries"] = 5
        h1 = hash_manifest(m1)
        h2 = hash_manifest(m2)
        assert h1 == h2

    def test_non_model_surfaces_unaffected(self):
        """Quantization should only apply to model_runtime."""
        m1 = {
            "contract": {
                "prompt_stack": {"key": "value"},
            }
        }
        m2 = {
            "contract": {
                "prompt_stack": {"key": "value"},
            }
        }
        assert hash_manifest(m1) == hash_manifest(m2)


# ── New Manifest Fields ──────────────────────────────────────────


class TestManifestStatus:
    """Test the new status field on AgentManifest."""

    def _minimal_data(self) -> dict:
        return {
            "spec_version": "0.2.0",
            "kind": "agent_manifest",
            "manifest_id": "amf_test",
            "agent_name": "test",
            "version_label": "v1",
            "created_at": "2026-01-01T00:00:00Z",
            "identity": {"overall_hash": "sha256:abc"},
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "x", "model": "y"},
                "tool_registry": {"registry_version": "1", "registry_hash": "h", "tools": []},
                "workflow": {},
                "output_contract": {"version": "1", "schema_hash": "h", "format": "text", "strict": False},
            },
        }

    def test_status_defaults_to_none(self):
        m = AgentManifest.model_validate(self._minimal_data())
        assert m.status is None

    def test_status_active(self):
        data = self._minimal_data()
        data["status"] = "active"
        m = AgentManifest.model_validate(data)
        assert m.status == "active"

    def test_status_deprecated(self):
        data = self._minimal_data()
        data["status"] = "deprecated"
        m = AgentManifest.model_validate(data)
        assert m.status == "deprecated"

    def test_invalid_status_rejected(self):
        data = self._minimal_data()
        data["status"] = "invalid"
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)


class TestManifestCapabilities:
    """Test the new capabilities field on AgentManifest."""

    def _minimal_data(self) -> dict:
        return {
            "spec_version": "0.2.0",
            "kind": "agent_manifest",
            "manifest_id": "amf_test",
            "agent_name": "test",
            "version_label": "v1",
            "created_at": "2026-01-01T00:00:00Z",
            "identity": {"overall_hash": "sha256:abc"},
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "x", "model": "y"},
                "tool_registry": {"registry_version": "1", "registry_hash": "h", "tools": []},
                "workflow": {},
                "output_contract": {"version": "1", "schema_hash": "h", "format": "text", "strict": False},
            },
        }

    def test_capabilities_defaults_to_none(self):
        m = AgentManifest.model_validate(self._minimal_data())
        assert m.capabilities is None

    def test_capabilities_set(self):
        data = self._minimal_data()
        data["capabilities"] = {
            "streaming": True,
            "multi_turn": True,
            "modalities": ["text", "image"],
        }
        m = AgentManifest.model_validate(data)
        assert m.capabilities["streaming"] is True
        assert "image" in m.capabilities["modalities"]


class TestToolDescriptorNewFields:
    """Test new fields on ToolDescriptor: description, annotations, optional version."""

    def test_version_is_optional(self):
        tool = ToolDescriptor(name="my_tool", hash="sha256:abc")
        assert tool.version is None

    def test_version_still_works(self):
        tool = ToolDescriptor(name="my_tool", version="1", hash="sha256:abc")
        assert tool.version == "1"

    def test_description_field(self):
        tool = ToolDescriptor(
            name="search",
            hash="sha256:abc",
            description="Search the knowledge base",
        )
        assert tool.description == "Search the knowledge base"

    def test_annotations_field(self):
        tool = ToolDescriptor(
            name="delete_file",
            hash="sha256:abc",
            annotations={
                "destructive": True,
                "requires_confirmation": True,
                "read_only_hint": False,
            },
        )
        assert tool.annotations["destructive"] is True

    def test_description_defaults_to_none(self):
        tool = ToolDescriptor(name="t", hash="h")
        assert tool.description is None
        assert tool.annotations is None


class TestOutputContractModalities:
    """Test the new modalities field on OutputContract."""

    def test_defaults_to_empty(self):
        oc = OutputContract(version="1", schema_hash="h", format="text")
        assert oc.modalities == []

    def test_set_modalities(self):
        oc = OutputContract(
            version="1",
            schema_hash="h",
            format="text",
            modalities=["text", "image", "audio"],
        )
        assert "image" in oc.modalities
        assert len(oc.modalities) == 3


class TestGenerationConfigNoHash:
    """Verify generation_config_hash was removed."""

    def test_no_generation_config_hash_field(self):
        gc = GenerationConfig(temperature=0.5)
        data = gc.model_dump()
        assert "generation_config_hash" not in data


# ── Condition DSL ────────────────────────────────────────────────


class TestConditionDSL:
    """Test the formalized condition DSL for compatibility batch rules."""

    def test_single_surface_token(self):
        assert validate_condition("tool_surface_unchanged") is True

    def test_and_combination(self):
        assert validate_condition("tool_surface_unchanged AND prompt_surface_unchanged") is True

    def test_or_combination(self):
        assert validate_condition("model_changed OR workflow_changed") is True

    def test_parameterized_token(self):
        assert validate_condition("tool_missing:search_population") is True

    def test_complex_condition(self):
        assert validate_condition(
            "output_contract_changed AND episode_uses_format:json"
        ) is True

    def test_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Unknown condition token"):
            validate_condition("completely_invalid_thing")

    def test_invalid_parameterized_token_raises(self):
        with pytest.raises(ValueError, match="Unknown parameterized condition token"):
            validate_condition("invalid_param:value")

    def test_all_surfaces_unchanged(self):
        assert validate_condition("all_surfaces_unchanged") is True

    def test_classification_rule_validates(self):
        rule = ClassificationRule(
            rule_id="r1",
            condition="tool_surface_unchanged AND prompt_surface_unchanged",
            decision="keep",
            matched_count=50,
        )
        assert rule.condition == "tool_surface_unchanged AND prompt_surface_unchanged"

    def test_classification_rule_rejects_invalid(self):
        with pytest.raises(Exception):
            ClassificationRule(
                rule_id="r1",
                condition="bad_token",
                decision="keep",
                matched_count=0,
            )


# ── New JSON Schema Validation ───────────────────────────────────


class TestNewJsonSchemas:
    """Test that Pydantic models validate against the new JSON schemas."""

    def test_episode_schema_validates(self):
        import jsonschema

        from agentversion.dataset import Episode

        episode = Episode(
            episode_id="ep1",
            task_id="t1",
            status="success",
        )
        schema = json.load(open("schemas/episode.schema.json"))
        jsonschema.validate(json.loads(episode.model_dump_json()), schema)

    def test_step_schema_validates(self):
        import jsonschema

        from agentversion.dataset import Step

        step = Step(
            step_id="s1",
            episode_id="ep1",
            index=0,
            step_type="llm_call",
        )
        schema = json.load(open("schemas/step.schema.json"))
        jsonschema.validate(json.loads(step.model_dump_json()), schema)

    def test_dataset_snapshot_schema_validates(self):
        import jsonschema

        from agentversion.dataset import DatasetSnapshot

        snap = DatasetSnapshot(
            snapshot_id="ds1",
            name="eval-set-v1",
            dataset_type="eval",
            created_at="2026-01-01T00:00:00Z",
        )
        schema = json.load(open("schemas/dataset-snapshot.schema.json"))
        jsonschema.validate(json.loads(snap.model_dump_json()), schema)

    def test_replay_result_schema_validates(self):
        import jsonschema

        from agentversion.replay import ReplayResult

        result = ReplayResult(
            replay_job_id="rj1",
            status="completed",
            target_manifest_id="amf_1",
        )
        schema = json.load(open("schemas/replay-result.schema.json"))
        jsonschema.validate(json.loads(result.model_dump_json()), schema)

    def test_compatibility_batch_schema_validates(self):
        import jsonschema

        from agentversion.decision import CompatibilityBatch, CompatibilityBatchSummary

        batch = CompatibilityBatch(
            batch_id="rb1",
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            created_at="2026-01-01T00:00:00Z",
            summary=CompatibilityBatchSummary(
                total_episodes=100, keep=80, repair=10, replay=8, drop=2,
            ),
            classification_rules=[
                ClassificationRule(
                    rule_id="r1",
                    condition="tool_surface_unchanged",
                    decision="keep",
                    matched_count=80,
                ),
            ],
        )
        schema = json.load(open("schemas/compatibility-batch.schema.json"))
        jsonschema.validate(json.loads(batch.model_dump_json()), schema)


# ── agent-manifest schema ↔ model reconciliation ───────────


class TestAgentManifestSchemaReconciliation:
    """The bundled ``agent-manifest.schema.json`` and the
    ``AgentManifest`` pydantic model must accept the SAME documents. The schema is
    reconciled TO the model (runtime truth):

      - ``spec_version`` / ``kind`` are model-defaulted  -> NOT schema-required
      - ``output_contract.strict`` is model-defaulted     -> NOT schema-required
      - ``SubagentDescriptor.version`` is model-required+non-null
                                                            -> schema-required+non-null

    The main manifest schema previously had NO model-vs-schema round-trip test (the
    other sibling schemas in TestNewJsonSchemas do); the minimal fixtures elsewhere
    use a non-ULID ``manifest_id`` that the schema's pattern rejects, so this gap
    went unguarded. This class IS that guard.
    """

    @staticmethod
    def _schema() -> dict:
        return json.load(open("schemas/agent-manifest.schema.json"))

    @staticmethod
    def _full_manifest() -> dict:
        return {
            "spec_version": "1.0.0",
            "kind": "agent_manifest",
            # ULID form required by the schema's manifest_id pattern.
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "agent_name": "test-agent",
            "version_label": "v1",
            "created_at": "2026-01-01T00:00:00Z",
            "identity": {"overall_hash": "sha256:abc"},
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "x", "model": "y"},
                "tool_registry": {"registry_version": "1", "registry_hash": "h", "tools": []},
                "workflow": {},
                "subagents": [{"name": "sub", "version": "v1", "hash": "h"}],
                "output_contract": {"version": "1", "schema_hash": "h", "format": "text"},
            },
        }

    def test_model_output_validates_against_schema(self):
        import jsonschema

        m = AgentManifest.model_validate(self._full_manifest())
        jsonschema.validate(json.loads(m.model_dump_json()), self._schema())

    def test_spec_version_and_kind_optional_in_both(self):
        """Model defaults spec_version/kind; the schema must accept their omission too."""
        import jsonschema

        data = self._full_manifest()
        data.pop("spec_version")
        data.pop("kind")
        m = AgentManifest.model_validate(data)  # model fills the defaults
        assert m.spec_version and m.kind == "agent_manifest"
        jsonschema.validate(data, self._schema())  # schema no longer requires them

    def test_output_contract_strict_optional_in_both(self):
        """Model defaults strict=False; the schema must accept its omission too."""
        import jsonschema

        data = self._full_manifest()
        data["contract"]["output_contract"].pop("strict", None)
        m = AgentManifest.model_validate(data)
        assert m.contract.output_contract.strict is False
        jsonschema.validate(data, self._schema())

    def test_subagent_missing_version_rejected_by_both(self):
        """Inverse drift: SubagentDescriptor.version is model-required+non-null, so the
        schema must require it too. A subagent without version must be rejected by BOTH.
        """
        import jsonschema

        data = self._full_manifest()
        data["contract"]["subagents"] = [{"name": "sub", "hash": "h"}]  # no version
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(data, self._schema())
        with pytest.raises(Exception):  # pydantic ValidationError
            AgentManifest.model_validate(data)

    def test_subagent_null_version_rejected_by_both(self):
        """A null version must also fail both (schema version is non-nullable)."""
        import jsonschema

        data = self._full_manifest()
        data["contract"]["subagents"] = [{"name": "sub", "version": None, "hash": "h"}]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(data, self._schema())
        with pytest.raises(Exception):
            AgentManifest.model_validate(data)


# ── Example Manifest Validation ──────────────────────────────────


class TestExampleManifestsV020:
    """Verify updated example manifests parse and validate."""

    def test_v1_has_new_fields(self):
        with open("examples/manifest/finance-agent-v1.json") as f:
            data = json.load(f)
        m = AgentManifest.model_validate(data)
        assert m.spec_version == "1.0.0"
        assert m.status == "active"
        assert m.capabilities is not None
        assert m.capabilities["tool_use"] is True
        # Tools should have descriptions
        for tool in m.contract.tool_registry.tools:
            assert tool.description is not None
        # Output contract should have modalities
        assert "text" in m.contract.output_contract.modalities

    def test_v2_has_tool_annotations(self):
        with open("examples/manifest/finance-agent-v2.json") as f:
            data = json.load(f)
        m = AgentManifest.model_validate(data)
        # write_spreadsheet_cell should have annotations
        ws_tool = next(t for t in m.contract.tool_registry.tools if t.name == "write_spreadsheet_cell")
        assert ws_tool.annotations is not None
        assert ws_tool.annotations["destructive"] is True

    def test_v2_no_generation_config_hash(self):
        with open("examples/manifest/finance-agent-v2.json") as f:
            data = json.load(f)
        gen_config = data["contract"]["model_runtime"]["generation_config"]
        assert "generation_config_hash" not in gen_config
