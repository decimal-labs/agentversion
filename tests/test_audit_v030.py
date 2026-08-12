"""Regression tests for the v0.2.0 correctness audit.

Each test below pins a bug the prior 362-test suite passed straight over — the
schemas rejecting what the code emits, the inverted output_contract severity, the
asymmetric add/remove diffs, the model-family regex missing compact dates, and the
unvalidated reason codes. See CHANGELOG.md (0.2.0, ### Fixed).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentversion.compatibility import classify_compatibility
from agentversion.decision import REASON_CODES, CompatibilityDecision, DecisionSubject
from agentversion.diff import (
    _extract_model_family,
    diff_manifests,
    model_severity,
    output_contract_severity,
)
from agentversion.validator import validate_manifest

_REPO = Path(__file__).resolve().parent.parent
_SCHEMA_DIR = _REPO / "schemas"
_EXAMPLE_V1 = _REPO / "examples" / "manifest" / "finance-agent-v1.json"

_BASE = {
    "prompt_stack": {"system_prompt": {"id": "p", "version": "1", "hash": "sha256:a"}},
    "model_runtime": {"provider": "openai", "model": "gpt-4o"},
    "tool_registry": {"registry_version": "1", "registry_hash": "sha256:b", "tools": []},
    "output_contract": {
        "version": "1", "schema_hash": "sha256:d", "format": "text", "strict": False,
    },
}


def _load_schema(name: str) -> dict:
    return json.loads((_SCHEMA_DIR / name).read_text())


def _m(mid: str, **extra) -> dict:
    return {"manifest_id": mid, "contract": {**_BASE, **extra}}


def _policy(threshold, policy_hash):
    return {"policy_hash": policy_hash, "objection_threshold": threshold,
            "concede_events": ["offered_refund"], "always_forbidden": ["admits_liability"]}


def _decision(**kw):
    base = dict(
        decision_id="cd_1",
        subject=DecisionSubject(type="episode", id="e1"),
        old_manifest_id="amf_old",
        target_manifest_id="amf_new",
        decision="replay",
        reason_codes=[],
        created_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )
    base.update(kw)
    return CompatibilityDecision(**base)


# ── 0a: behavioral_policy 3-way schema drift ──────────────────────────────────


class TestBehavioralPolicySchemaDrift:
    def test_behavioral_policy_diff_validates_against_its_schema(self):
        import jsonschema

        old = _m("amf_old", behavioral_policy=_policy(3, "sha256:P1"))
        new = _m("amf_new", behavioral_policy=_policy(1, "sha256:P2"))
        out = json.loads(diff_manifests(old, new).model_dump_json())
        assert any(c["surface"] == "behavioral_policy" for c in out["changed_surfaces"])
        # Previously raised: 'behavioral_policy' not in the surface enum.
        jsonschema.validate(out, _load_schema("manifest-diff.schema.json"))

    def test_behavioral_policy_changed_is_a_valid_reason_code(self):
        import jsonschema

        assert "behavioral_policy_changed" in REASON_CODES
        dec = _decision(reason_codes=["behavioral_policy_changed"])
        jsonschema.validate(
            json.loads(dec.model_dump_json()),
            _load_schema("compatibility-decision.schema.json"),
        )


# ── 0b: model_runtime reason code ─────────────────────────────────────────────


class TestModelRuntimeReasonCode:
    def test_model_runtime_changed_is_in_reason_codes(self):
        assert "model_runtime_changed" in REASON_CODES

    def test_model_swap_reports_model_runtime_changed_not_prompt(self):
        old = _m("amf_old")
        new = _m("amf_new", model_runtime={"provider": "google", "model": "gemini-2.5-flash"})
        report = classify_compatibility(diff_manifests(old, new))
        assert "model_runtime_changed" in report.reason_codes
        assert "prompt_policy_changed" not in report.reason_codes


# ── 0c: output_contract severity (was inverted vs the spec) ───────────────────


class TestOutputContractSeverity:
    def test_format_change_is_minor(self):
        sev, _ = output_contract_severity({"format": "text"}, {"format": "json"})
        assert sev == "minor"

    def test_schema_change_is_moderate(self):
        sev, _ = output_contract_severity({"schema_hash": "sha256:a"}, {"schema_hash": "sha256:b"})
        assert sev == "moderate"

    def test_strict_toggle_is_major(self):
        sev, _ = output_contract_severity({"strict": False}, {"strict": True})
        assert sev == "major"

    def test_strict_dominates(self):
        sev, _ = output_contract_severity(
            {"format": "text", "schema_hash": "sha256:a", "strict": False},
            {"format": "json", "schema_hash": "sha256:b", "strict": True},
        )
        assert sev == "major"

    def test_strict_only_flip_is_breaking_major(self):
        old = _m("amf_old")
        new = _m("amf_new", output_contract={
            "version": "1", "schema_hash": "sha256:d", "format": "text", "strict": True,
        })
        oc = next(c for c in diff_manifests(old, new).changed_surfaces
                  if c.surface == "output_contract")
        assert (oc.change_type, oc.severity) == ("breaking", "major")


# ── 0d: add/remove routes through the dedicated classifier (symmetry) ─────────


def _surface_change(old_contract, new_contract, surface):
    d = diff_manifests({"manifest_id": "a", "contract": old_contract},
                       {"manifest_id": "b", "contract": new_contract})
    return next((c for c in d.changed_surfaces if c.surface == surface), None)


class TestAddRemoveSymmetry:
    _MINIMAL = {"prompt_stack": _BASE["prompt_stack"]}

    def test_tool_registry_add_is_minor_remove_is_major(self):
        tr = {"registry_version": "1", "registry_hash": "sha256:x",
              "tools": [{"name": "t", "version": "1", "hash": "sha256:h",
                         "input_schema_hash": "sha256:i", "output_schema_hash": "sha256:o"}]}
        with_tr = {**self._MINIMAL, "tool_registry": tr}
        add = _surface_change(self._MINIMAL, with_tr, "tool_registry")
        rm = _surface_change(with_tr, self._MINIMAL, "tool_registry")
        # A whole registry appearing is now member-level "add" (minor), NOT the
        # old flat generic "moderate".
        assert (add.change_type, add.severity) == ("non_breaking", "minor")
        assert (rm.change_type, rm.severity) == ("breaking", "major")

    def test_output_contract_add_and_remove_are_breaking(self):
        oc = {"version": "1", "schema_hash": "sha256:s", "format": "json", "strict": True}
        with_oc = {**self._MINIMAL, "output_contract": oc}
        add = _surface_change(self._MINIMAL, with_oc, "output_contract")
        rm = _surface_change(with_oc, self._MINIMAL, "output_contract")
        assert add.change_type == "breaking"
        assert rm.change_type == "breaking"

    def test_subagents_add_is_breaking_moderate_remove_is_major(self):
        sa = [{"name": "billing", "hash": "sha256:b1"}]
        with_sa = {**self._MINIMAL, "subagents": sa}
        add = _surface_change(self._MINIMAL, with_sa, "subagents")
        rm = _surface_change(with_sa, self._MINIMAL, "subagents")
        assert (add.change_type, add.severity) == ("breaking", "moderate")
        assert (rm.change_type, rm.severity) == ("breaking", "major")

    def test_behavioral_policy_introduce_non_breaking_remove_breaking(self):
        bp = _policy(3, "sha256:P")
        with_bp = {**self._MINIMAL, "behavioral_policy": bp}
        add = _surface_change(self._MINIMAL, with_bp, "behavioral_policy")
        rm = _surface_change(with_bp, self._MINIMAL, "behavioral_policy")
        assert add.change_type == "non_breaking"
        assert rm.change_type == "breaking"


# ── 0e: model-family regex (compact Anthropic dates) ──────────────────────────


class TestModelFamilyExtraction:
    @pytest.mark.parametrize("model,family", [
        ("claude-3-5-sonnet-20241022", "claude-3-5-sonnet"),
        ("claude-opus-4-20250514", "claude-opus-4"),
        ("gpt-4o-2024-08-06", "gpt-4o"),
        ("gpt-4o-mini-2024-07-18", "gpt-4o"),
        ("gpt-4o-mini", "gpt-4o"),
        ("gpt-4", "gpt-4"),
    ])
    def test_extract_family(self, model, family):
        assert _extract_model_family(model) == family

    @pytest.mark.parametrize("a,b,expected", [
        # Date-revs of the same model are a version bump (moderate), not a family swap.
        ("claude-3-5-sonnet-20240620", "claude-3-5-sonnet-20241022", "moderate"),
        ("claude-opus-4-20250514", "claude-opus-4-20251001", "moderate"),
        ("gpt-4o-2024-08-06", "gpt-4o-2024-11-20", "moderate"),
        # A genuine family change stays major (no over-stripping).
        ("gpt-4", "gpt-4o", "major"),
    ])
    def test_model_severity_date_rev_vs_family(self, a, b, expected):
        sev, _ = model_severity({"provider": "x", "model": a}, {"provider": "x", "model": b})
        assert sev == expected


# ── 0f: validator (reason-code enforcement, schema pass, NaN escalation) ──────


class TestValidatorHardening:
    def test_unknown_reason_code_rejected(self):
        with pytest.raises(ValueError, match="Unknown reason_codes"):
            _decision(reason_codes=["not_a_real_code"])

    def test_new_reason_codes_accepted(self):
        dec = _decision(reason_codes=["model_runtime_changed", "behavioral_policy_changed"])
        assert dec.reason_codes == ["model_runtime_changed", "behavioral_policy_changed"]

    def test_check_schema_flags_unknown_top_level_key(self):
        data = json.loads(_EXAMPLE_V1.read_text())
        data["bogus_top_level"] = 123
        # Default: Pydantic silently drops the unknown key → no schema_violation.
        default = validate_manifest(data, check_hash=False)
        assert not any(i.code == "schema_violation" for i in default.issues)
        # Opt-in: the schema's additionalProperties:false catches it.
        strict = validate_manifest(data, check_hash=False, check_schema=True)
        assert any(i.code == "schema_violation" for i in strict.issues)

    def test_non_finite_float_makes_manifest_invalid(self):
        data = json.loads(_EXAMPLE_V1.read_text())
        # Inject a non-finite float via the contract extension hatch (extra='allow').
        data["contract"]["custom_surface"] = {"bad": float("nan")}
        res = validate_manifest(data, check_hash=True)
        assert not res.valid
        assert any(i.code == "hash_uncomputable" for i in res.issues)
