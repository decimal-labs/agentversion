"""agentversion manifest → A2A (Agent2Agent) Agent Card projection. The card advertises the agent (the
A2A interop standard); agentversion adds the versioned-contract + provenance layer A2A omits."""
from agentversion import manifest_to_agent_card
from agentversion.a2a import A2A_PROTOCOL_VERSION


def _manifest() -> dict:
    return {
        "spec_version": "1.0.0",
        "kind": "agent_manifest",
        "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
        "agent_name": "support-agent",
        "version_label": "v2",
        "description": "Handles refunds and escalations.",
        "created_at": "2026-03-10T10:00:00Z",
        "created_by": {"organization": "DecimalAI"},
        "capabilities": {"streaming": True},
        "identity": {"overall_hash": "sha256:deadbeef", "hash_algorithm": "jcs-sha256"},
        "contract": {
            "prompt_stack": {"system_prompt": {"id": "p", "version": "1", "hash": "sha256:a"}},
            "model_runtime": {"provider": "openai", "model": "gpt-4o"},
            "tool_registry": {"registry_version": "1", "registry_hash": "sha256:b", "tools": []},
            "workflow": {},
            "output_contract": {"version": "1", "schema_hash": "sha256:d", "format": "json", "strict": True},
            "skill_registry": {
                "registry_version": "1", "registry_hash": "sha256:s",
                "skills": [
                    {"name": "refund-policy", "version": "1", "hash": "sha256:r",
                     "description": "Apply the refund policy", "tags": ["support", "billing"]},
                ],
            },
        },
    }


def test_core_fields_map():
    card = manifest_to_agent_card(_manifest(), url="https://agents.example/support")
    assert card["protocolVersion"] == A2A_PROTOCOL_VERSION
    assert card["name"] == "support-agent"
    assert card["version"] == "v2"
    assert card["description"].startswith("Handles refunds")
    assert card["url"] == "https://agents.example/support"
    assert card["provider"] == {"organization": "DecimalAI"}


def test_capabilities_and_output_modes():
    card = manifest_to_agent_card(_manifest())
    assert card["capabilities"]["streaming"] is True
    assert card["capabilities"]["pushNotifications"] is False
    # output_contract.format == "json" → application/json
    assert card["defaultOutputModes"] == ["application/json"]


def test_skills_project_from_skill_registry():
    card = manifest_to_agent_card(_manifest())
    assert len(card["skills"]) == 1
    skill = card["skills"][0]
    assert skill["id"] == "refund-policy" and skill["name"] == "refund-policy"
    assert skill["tags"] == ["support", "billing"]


def test_provenance_block_pins_the_exact_version():
    # The differentiation: the card carries the manifest identity so a consumer can resolve EXACTLY
    # which versioned contract it describes — what A2A cards alone cannot do.
    card = manifest_to_agent_card(_manifest())
    prov = card["x-agentversion"]
    assert prov["manifest_id"] == "amf_01HZK1A2B3C4D5E6F7G8H9J0K1"
    assert prov["overall_hash"] == "sha256:deadbeef"
    assert prov["spec_version"] == "1.0.0"


def test_url_omitted_when_not_supplied():
    # url is a deployment concern, not part of the internal contract.
    assert "url" not in manifest_to_agent_card(_manifest())


def test_accepts_agentmanifest_model():
    from agentversion.hasher import compute_and_set_hashes
    from agentversion.manifest import AgentManifest

    data = _manifest()
    data.pop("created_by", None)  # the strict CreatedBy model needs more than the dict-path shape
    compute_and_set_hashes(data)
    card = manifest_to_agent_card(AgentManifest.model_validate(data))
    assert card["name"] == "support-agent"
    assert card["x-agentversion"]["overall_hash"] == data["identity"]["overall_hash"]
