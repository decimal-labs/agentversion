"""The canonical component_type → surface routing is the single source of truth shared by the SDK
exporter and the platform's diff translators, so the singular→plural `guardrail` rename (and any new
component type) can't drift between producer and consumer. The SDK + backend each have a
parity test asserting they route via this map."""
from agentversion import COMPONENT_TYPE_TO_SURFACE, SURFACE_KEYS, surface_key_for_component


def test_guardrail_maps_to_plural_surface():
    # The rename that previously had to be hand-applied in every translator copy.
    assert surface_key_for_component("guardrail") == "guardrails"


def test_unknown_type_maps_to_itself():
    # A new/custom component type is diffed generically under its own key rather than dropped.
    assert surface_key_for_component("some_custom_surface") == "some_custom_surface"


def test_every_mapped_surface_is_a_known_surface_key():
    # A mapping must never route to a surface the diff engine doesn't know — that would lose the
    # surface's reason codes and diff it generically.
    for ctype, surface in COMPONENT_TYPE_TO_SURFACE.items():
        assert surface in SURFACE_KEYS, f"{ctype} -> {surface} is not a known SURFACE_KEY"


def test_canonical_routing_is_pinned():
    # Pin the exact map so a change is a deliberate, reviewed edit that must land in lockstep with the
    # SDK + backend parity tests.
    assert COMPONENT_TYPE_TO_SURFACE == {
        "tool": "tool_registry",
        "skill": "skill_registry",
        "subagent": "subagents",
        "prompt": "prompt_stack",
        "model": "model_runtime",
        "output_schema": "output_contract",
        "workflow": "workflow",
        "guardrail": "guardrails",
    }
