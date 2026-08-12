"""Tests for ``agentversion.contract.contract_from_components`` — the shared
flat-components → contract-surface assembly used by the SDK exporter and the
platform diff/hash path, so they can't drift on the identity hash.
"""
from __future__ import annotations

from agentversion.contract import contract_from_components, quantize_float
from agentversion.hasher import hash_manifest
from agentversion.validator import validate_manifest


def _comp(ctype, name, version=None, content_hash=None, schema_json=None):
    return {"component_type": ctype, "component_name": name, "component_version": version,
            "content_hash": content_hash, "schema_json": schema_json}


def test_required_surfaces_always_present():
    contract = contract_from_components([])
    assert set(contract) == {"prompt_stack", "model_runtime", "tool_registry",
                             "workflow", "output_contract"}
    # output_contract synthesizes the "none" sentinel when undeclared.
    assert contract["output_contract"]["format"] == "none"
    assert contract["model_runtime"] == {"provider": "unknown", "model": "unknown"}


def test_prompt_slot_assignment():
    c = contract_from_components([
        _comp("prompt", "system", content_hash="sha256:s"),
        _comp("prompt", "developer", content_hash="sha256:d"),
    ])
    assert c["prompt_stack"]["system_prompt"]["hash"] == "sha256:s"
    assert c["prompt_stack"]["developer_prompt"]["hash"] == "sha256:d"


def test_unnamed_prompts_fill_open_slots_in_order():
    c = contract_from_components([
        _comp("prompt", "foo", content_hash="sha256:1"),
        _comp("prompt", "bar", content_hash="sha256:2"),
    ])
    assert c["prompt_stack"]["system_prompt"]["hash"] == "sha256:1"
    assert c["prompt_stack"]["developer_prompt"]["hash"] == "sha256:2"


def test_model_runtime_quantizes_generation_config():
    c = contract_from_components([
        _comp("model", "default", version="gpt-4o", content_hash="sha256:m",
              schema_json={"provider": "openai", "model": "gpt-4o",
                           "temperature": 0.71, "top_p": 0.93}),
    ])
    gc = c["model_runtime"]["generation_config"]
    assert gc["temperature"] == quantize_float(0.71, 0.1) == 0.7
    assert gc["top_p"] == quantize_float(0.93, 0.05)


def test_model_provider_inferred_when_absent():
    c = contract_from_components([
        _comp("model", "default", schema_json={"model": "claude-haiku-4-5"}),
    ])
    assert c["model_runtime"]["provider"] == "anthropic"


# ── New 0.2.0 surfaces (must mirror the SDK exporter) ───────────────────────

def test_model_runtime_lifts_tool_calling_mode_and_runtime_version():
    """tool_calling_mode + runtime_version are TOP-LEVEL model_runtime
    fields (not under generation_config), so the diff classifies them."""
    c = contract_from_components([
        _comp("model", "default", content_hash="sha256:m",
              schema_json={"provider": "openai", "model": "gpt-4o",
                           "tool_calling_mode": "native", "runtime_version": "1.2"}),
    ])
    mr = c["model_runtime"]
    assert mr["tool_calling_mode"] == "native"
    assert mr["runtime_version"] == "1.2"
    assert "tool_calling_mode" not in mr.get("generation_config", {})


def test_behavioral_policy_surface_assembled():
    """behavioral_policy is emitted verbatim from its schema_json."""
    sj = {"policy_id": "refund", "policy_hash": "sha256:p", "objection_threshold": 3,
          "always_forbidden": ["admit_liability"]}
    c = contract_from_components([
        _comp("model", "default", schema_json={"model": "gpt-4o"}),
        _comp("behavioral_policy", "behavioral_policy", content_hash="sha256:p", schema_json=sj),
    ])
    assert c["behavioral_policy"] == sj


def test_environment_surface_assembled():
    """environment is emitted verbatim from its schema_json."""
    sj = {"deployment_id": "d", "region": "us", "runtime_versions": {"python": "3.12"}}
    c = contract_from_components([
        _comp("model", "default", schema_json={"model": "gpt-4o"}),
        _comp("environment", "environment", content_hash="sha256:e", schema_json=sj),
    ])
    assert c["environment"] == sj


def test_new_optional_surfaces_absent_when_undeclared():
    """Additive-only: a model-only contract carries neither new surface, so
    existing manifests keep their exact prior identity hash."""
    c = contract_from_components([_comp("model", "default", schema_json={"model": "gpt-4o"})])
    assert "behavioral_policy" not in c
    assert "environment" not in c


def test_behavioral_policy_participates_in_identity_hash():
    """Adding behavioral_policy, and changing its policy_hash, each change the
    canonical jcs-sha256 identity hash."""
    base = [_comp("model", "default", content_hash="sha256:m",
                  schema_json={"provider": "openai", "model": "gpt-4o"})]
    with_p = base + [_comp("behavioral_policy", "behavioral_policy", content_hash="sha256:p",
                           schema_json={"policy_id": "p", "policy_hash": "sha256:p"})]
    with_p2 = base + [_comp("behavioral_policy", "behavioral_policy", content_hash="sha256:p2",
                            schema_json={"policy_id": "p", "policy_hash": "sha256:p2"})]
    h_base = hash_manifest({"contract": contract_from_components(base)})
    h_p = hash_manifest({"contract": contract_from_components(with_p)})
    h_p2 = hash_manifest({"contract": contract_from_components(with_p2)})
    assert h_base != h_p   # the surface participates in identity
    assert h_p != h_p2     # a rule change re-versions


def test_tool_and_skill_registry_hashes_are_computed():
    c = contract_from_components([
        _comp("tool", "t1", version="1", content_hash="sha256:t1",
              schema_json={"input_schema_hash": "sha256:i", "description": "d"}),
        _comp("skill", "s1", content_hash="sha256:s1", schema_json={"description": "x"}),
    ])
    assert c["tool_registry"]["registry_hash"]            # non-empty
    assert c["tool_registry"]["tools"][0]["name"] == "t1"
    assert c["skill_registry"]["registry_hash"]
    assert c["skill_registry"]["skills"][0]["name"] == "s1"


def test_optional_surfaces_only_when_declared():
    bare = contract_from_components([_comp("model", "m", schema_json={"model": "gpt-4o"})])
    assert "subagents" not in bare and "guardrails" not in bare and "context_config" not in bare

    rich = contract_from_components([
        _comp("subagent", "billing", version="1", content_hash="sha256:sa"),
        _comp("guardrail", "pii", content_hash="sha256:g", schema_json={"kind": "pii"}),
        _comp("context_config", "ctx", content_hash="sha256:c"),
    ])
    assert rich["subagents"][0]["name"] == "billing"
    assert rich["guardrails"]["bundle_hash"]
    assert rich["context_config"]["retrieval_config_hash"] == "sha256:c"


def test_assembled_contract_is_hashable_and_deterministic():
    comps = [
        _comp("tool", "t", content_hash="sha256:t",
              schema_json={"input_schema_hash": "sha256:i"}),
        _comp("model", "default", schema_json={"provider": "openai", "model": "gpt-4o"}),
    ]
    h1 = hash_manifest({"contract": contract_from_components(comps)})
    h2 = hash_manifest({"contract": contract_from_components(list(reversed(comps)))})
    assert h1 == h2 and h1.startswith("sha256:")


def test_assembled_manifest_validates():
    contract = contract_from_components([
        _comp("prompt", "system", content_hash="sha256:p"),
        _comp("model", "default", schema_json={"provider": "openai", "model": "gpt-4o"}),
        _comp("tool", "t", content_hash="sha256:t"),
    ])
    manifest = {
        "spec_version": "1.0.0", "kind": "agent_manifest",
        "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
        "agent_name": "a", "version_label": "v1",
        "created_at": "2026-05-12T00:00:00Z",
        "identity": {"overall_hash": "", "hash_algorithm": "jcs-sha256"},
        "contract": contract,
    }
    manifest["identity"]["overall_hash"] = hash_manifest(manifest)
    res = validate_manifest(manifest)
    assert res.valid, [i.message for i in res.errors]
