"""behavioral_policy is a first-class contract surface so a multi-turn policy FLIP (e.g. a refund
escalation threshold 3 → 1, or removing an `always_forbidden` rule) diffs as BREAKING — not silently
`keep`, which is what happened when the policy lived only inside the prompt hash (a prompt change is
non_breaking). Bound to skillevaluation's conversation-mode `policy_check`.

The surface is optional and omitted by default, so adding it does NOT change the `overall_hash` of any
existing (policy-less) manifest — the hasher only hashes surfaces actually present in the contract."""
from agentversion.compatibility import classify_compatibility
from agentversion.diff import diff_manifests

_BASE = {
    "prompt_stack": {"system_prompt": {"id": "p", "version": "1", "hash": "sha256:a"}},
    "model_runtime": {"provider": "g", "model": "m"},
    "tool_registry": {"registry_version": "1", "registry_hash": "sha256:b", "tools": []},
    "workflow": {},
    "output_contract": {"version": "1", "schema_hash": "sha256:d", "format": "text", "strict": False},
}


def _policy(threshold, policy_hash):
    return {"policy_hash": policy_hash, "objection_threshold": threshold,
            "concede_events": ["offered_refund"], "always_forbidden": ["admits_liability"]}


def _m(mid, **extra):
    return {"manifest_id": mid, "contract": {**_BASE, **extra}}


def test_policy_flip_is_breaking_and_not_keep():
    # deny-until-3 → deny-until-1, with the prompt hash UNCHANGED. This is the case the prompt-stack
    # hash alone misses; the dedicated surface makes it breaking.
    old = _m("amf_old", behavioral_policy=_policy(3, "sha256:P1"))
    new = _m("amf_new", behavioral_policy=_policy(1, "sha256:P2"))
    d = diff_manifests(old, new)
    bp = next(c for c in d.changed_surfaces if c.surface == "behavioral_policy")
    assert bp.change_type == "breaking"
    report = classify_compatibility(d)
    assert report.recommended_decision != "keep"
    assert "behavioral_policy_changed" in report.reason_codes


def test_unchanged_policy_hash_is_not_a_rule_change():
    # Same policy by canonical hash; only policy_id metadata differs → non_breaking (no rule changed).
    old = _m("amf_old", behavioral_policy={"policy_hash": "sha256:P", "policy_id": "v1", "objection_threshold": 3})
    new = _m("amf_new", behavioral_policy={"policy_hash": "sha256:P", "policy_id": "v2", "objection_threshold": 3})
    d = diff_manifests(old, new)
    changed = {c.surface: c.change_type for c in d.changed_surfaces}
    assert changed.get("behavioral_policy", "non_breaking") == "non_breaking"


def test_introducing_a_policy_is_additive_non_breaking():
    # Adding a policy where there was none doesn't invalidate the OLD eval set (which tested no policy).
    d = diff_manifests(_m("amf_old"), _m("amf_new", behavioral_policy=_policy(3, "sha256:P")))
    bp = next((c for c in d.changed_surfaces if c.surface == "behavioral_policy"), None)
    assert bp is not None and bp.change_type == "non_breaking"


def test_removing_a_policy_is_breaking():
    # Past data graded under the policy is now ungoverned.
    d = diff_manifests(_m("amf_old", behavioral_policy=_policy(3, "sha256:P")), _m("amf_new"))
    bp = next(c for c in d.changed_surfaces if c.surface == "behavioral_policy")
    assert bp.change_type == "breaking"


def test_absent_policy_is_not_injected_into_the_hashable_contract():
    # Hash-safety (the moat): the new optional field must NOT appear in a policy-less manifest's
    # serialized contract, so its overall_hash is unchanged from before the surface existed.
    from agentversion.manifest import AgentContract
    dumped = AgentContract.model_validate(dict(_BASE)).model_dump(mode="json", exclude_none=True)
    assert "behavioral_policy" not in dumped
