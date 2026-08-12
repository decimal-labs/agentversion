"""extra='allow' on AgentContract is the extension hatch: a custom/emerging surface (RAG
corpus, MCP server registry, memory policy, a vendor extension) is hashed by the hasher (which hashes
every contract key) and diffed by the engine (SURFACE_KEYS ∪ the actual keys), so it MUST survive
model_validate too. Before this, an unknown surface was silently DROPPED on validate, so a
validate→re-serialize→re-hash round-trip changed overall_hash — a moat-breaking non-determinism."""
from agentversion.diff import diff_manifests
from agentversion.hasher import hash_surface
from agentversion.manifest import AgentContract


def _contract_with_custom_surface() -> dict:
    return {
        "prompt_stack": {"system_prompt": {"id": "p", "version": "1", "hash": "sha256:a"}},
        "model_runtime": {"provider": "g", "model": "m"},
        "tool_registry": {"registry_version": "1", "registry_hash": "sha256:b", "tools": []},
        "workflow": {},
        "output_contract": {"version": "1", "schema_hash": "sha256:d", "format": "text", "strict": False},
        "rag_corpus": {"index_hash": "sha256:zzz"},  # an unknown/custom surface
    }


def test_custom_surface_survives_validate():
    c = AgentContract.model_validate(_contract_with_custom_surface())
    assert "rag_corpus" in c.model_dump(), "extra='allow' must retain a custom surface"


def test_round_trip_is_idempotent_and_preserves_custom_surface():
    contract = _contract_with_custom_surface()
    d1 = AgentContract.model_validate(contract).model_dump(mode="json", exclude_none=True)
    d2 = AgentContract.model_validate(d1).model_dump(mode="json", exclude_none=True)
    assert d1 == d2, "the validated canonical form must be stable under re-validation"
    assert "rag_corpus" in d1
    # The custom surface's content hash is identical before and after the round-trip (no drift).
    assert hash_surface(d1["rag_corpus"]) == hash_surface(contract["rag_corpus"])


def test_custom_surface_change_is_diffed():
    old = {"contract": _contract_with_custom_surface()}
    new_contract = {**_contract_with_custom_surface(), "rag_corpus": {"index_hash": "sha256:NEW"}}
    result = diff_manifests(old, {"contract": new_contract})
    surfaces = {c.surface for c in result.changed_surfaces}
    assert "rag_corpus" in surfaces, "a custom surface change must be visible to the diff"
