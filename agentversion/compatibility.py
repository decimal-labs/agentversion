"""Compatibility classification for AgentVersion.

Given a diff between two manifests, classifies what action is needed
for existing data (keep / repair / replay / drop).

See spec/reference.md §3 for the compatibility decision taxonomy and
spec/compatibility-policy.md for the user-configurable policy schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agentversion.constants import SPEC_VERSION
from agentversion.diff import ManifestDiff

# --- Mapping: surface changes → reason codes ---

_SURFACE_TO_REASON_CODES: dict[str, list[str]] = {
    "prompt_stack": ["prompt_policy_changed", "prompt_format_changed"],
    "model_runtime": ["model_runtime_changed"],
    "tool_registry": ["tool_missing", "tool_schema_incompatible", "tool_semantics_changed"],
    "skill_registry": ["skill_missing", "skill_content_changed"],
    "workflow": ["workflow_surface_changed"],
    "subagents": ["subagent_interface_changed"],
    "output_contract": ["output_contract_changed"],
    "guardrails": ["guardrail_policy_changed"],
    "behavioral_policy": ["behavioral_policy_changed"],
    "context_config": ["context_config_changed"],
    "environment": [
        "region_changed",
        "infra_image_changed",
        "external_service_pin_changed",
        "runtime_version_changed",
    ],
}


# Decision priority — used when combining per-surface verdicts.
# Higher number = more conservative (overrides milder verdicts).
PolicyAction = Literal["keep", "repair", "flag", "replay", "drop"]
_ACTION_PRIORITY: dict[str, int] = {
    "keep": 0,
    "repair": 1,
    "flag": 2,
    "replay": 3,
    "drop": 4,
}


# --- Pydantic models ---


class SurfaceRules(BaseModel):
    """Per-severity action rules for a single contract surface."""

    on_minor: PolicyAction = "keep"
    on_moderate: PolicyAction = "flag"
    on_major: PolicyAction = "drop"


class CompatibilityPolicy(BaseModel):
    """User-configurable mapping from change severity to action per surface.

    See ``schemas/compatibility-policy.schema.json`` for the JSON Schema.
    """

    kind: Literal["compatibility_policy"] = "compatibility_policy"
    version: str = "0.1"
    name: str = "default"
    preset: Literal["strict", "default", "permissive", "custom"] | None = "default"

    prompt_stack: SurfaceRules | None = None
    model_runtime: SurfaceRules | None = None
    tool_registry: SurfaceRules | None = None
    skill_registry: SurfaceRules | None = None
    workflow: SurfaceRules | None = None
    subagents: SurfaceRules | None = None
    output_contract: SurfaceRules | None = None
    guardrails: SurfaceRules | None = None
    behavioral_policy: SurfaceRules | None = None
    context_config: SurfaceRules | None = None
    environment: SurfaceRules | None = None

    def rules_for(self, surface: str) -> SurfaceRules:
        """Return rules for a surface, falling back to defaults if unset."""
        v = getattr(self, surface, None)
        return v if v is not None else SurfaceRules()


class CompatibilityReport(BaseModel):
    """Report summarizing the impact of a manifest change on existing data.

    Based on a diff, provides a recommended decision and the reason codes
    that led to that recommendation.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["compatibility_report"] = "compatibility_report"
    old_manifest_id: str
    new_manifest_id: str
    recommended_decision: Literal["keep", "repair", "replay", "drop"]
    reason_codes: list[str] = Field(default_factory=list)
    breaking_surfaces: list[str] = Field(default_factory=list)
    non_breaking_surfaces: list[str] = Field(default_factory=list)
    summary: str = ""


def _reason_codes_for(diff: ManifestDiff) -> list[str]:
    """Collect reason codes from every changed surface, preserving order."""
    out: list[str] = []
    for change in diff.changed_surfaces:
        for code in _SURFACE_TO_REASON_CODES.get(change.surface, []):
            if code not in out:
                out.append(code)
    return out


def _classify_with_default_rules(diff: ManifestDiff) -> CompatibilityReport:
    """Built-in fallback classifier when no policy is supplied."""
    breaking = [c for c in diff.changed_surfaces if c.change_type == "breaking"]
    non_breaking = [c for c in diff.changed_surfaces if c.change_type == "non_breaking"]
    breaking_names = [c.surface for c in breaking]
    non_breaking_names = [c.surface for c in non_breaking]
    reason_codes = _reason_codes_for(diff)

    if not breaking:
        return CompatibilityReport(
            old_manifest_id=diff.old_manifest_id,
            new_manifest_id=diff.new_manifest_id,
            recommended_decision="keep",
            reason_codes=reason_codes,
            breaking_surfaces=breaking_names,
            non_breaking_surfaces=non_breaking_names,
            summary="Only non-breaking changes — data remains valid.",
        )

    # Output-contract-only breaking change is repairable via schema migration.
    if breaking_names == ["output_contract"]:
        return CompatibilityReport(
            old_manifest_id=diff.old_manifest_id,
            new_manifest_id=diff.new_manifest_id,
            recommended_decision="repair",
            reason_codes=reason_codes,
            breaking_surfaces=breaking_names,
            non_breaking_surfaces=non_breaking_names,
            summary=(
                "Output contract changed — existing data may need schema migration "
                "but can be repaired without full replay."
            ),
        )

    return CompatibilityReport(
        old_manifest_id=diff.old_manifest_id,
        new_manifest_id=diff.new_manifest_id,
        recommended_decision="replay",
        reason_codes=reason_codes,
        breaking_surfaces=breaking_names,
        non_breaking_surfaces=non_breaking_names,
        summary=(
            f"Breaking changes in {', '.join(breaking_names)} — "
            f"existing data should be replayed against the new agent version."
        ),
    )


def _classify_with_policy(diff: ManifestDiff, policy: CompatibilityPolicy) -> CompatibilityReport:
    """Apply a user-supplied policy to derive the recommended decision.

    For each changed surface, look up ``policy.rules_for(surface).on_<severity>``.
    Combine per-surface actions by priority (drop > replay > flag > repair > keep).
    Map ``flag`` to ``replay`` for the report's ``recommended_decision`` since
    the report enum only has four values; the raw flag verdict is preserved in
    ``summary`` for callers that want it.
    """
    breaking_names = [c.surface for c in diff.changed_surfaces if c.change_type == "breaking"]
    non_breaking_names = [
        c.surface for c in diff.changed_surfaces if c.change_type == "non_breaking"
    ]
    reason_codes = _reason_codes_for(diff)

    per_surface: list[tuple[str, str]] = []  # (surface, action)
    for change in diff.changed_surfaces:
        rules = policy.rules_for(change.surface)
        if change.severity == "major":
            action = rules.on_major
        elif change.severity == "moderate":
            action = rules.on_moderate
        else:
            action = rules.on_minor
        per_surface.append((change.surface, action))

    if not per_surface:
        return CompatibilityReport(
            old_manifest_id=diff.old_manifest_id,
            new_manifest_id=diff.new_manifest_id,
            recommended_decision="keep",
            summary="No changes detected — all data remains valid.",
        )

    worst_surface, worst_action = max(per_surface, key=lambda sa: _ACTION_PRIORITY[sa[1]])

    # `flag` collapses to `replay` for the four-value enum (and the caller can
    # always re-derive the original per-surface verdicts).
    decision: Literal["keep", "repair", "replay", "drop"]
    if worst_action == "flag":
        decision = "replay"
    else:
        decision = worst_action  # type: ignore[assignment]

    summary = (
        f"Policy {policy.name!r}: worst surface = {worst_surface} → {worst_action}"
        + (f" (mapped to {decision})" if worst_action == "flag" else "")
    )

    return CompatibilityReport(
        old_manifest_id=diff.old_manifest_id,
        new_manifest_id=diff.new_manifest_id,
        recommended_decision=decision,
        reason_codes=reason_codes,
        breaking_surfaces=breaking_names,
        non_breaking_surfaces=non_breaking_names,
        summary=summary,
    )


def classify_compatibility(
    diff: ManifestDiff,
    policy: CompatibilityPolicy | None = None,
) -> CompatibilityReport:
    """Classify the compatibility impact of a manifest diff.

    Args:
        diff: A computed ``ManifestDiff``.
        policy: Optional user-configurable policy. When supplied, per-surface
            severity → action rules drive the decision. When omitted, the
            built-in fallback applies:

            - No changes → keep
            - Only non-breaking changes → keep
            - Breaking changes in ``output_contract`` only → repair
            - Any other breaking changes → replay

    Returns:
        A ``CompatibilityReport`` with the recommended decision.
    """
    if not diff.changed_surfaces:
        return CompatibilityReport(
            old_manifest_id=diff.old_manifest_id,
            new_manifest_id=diff.new_manifest_id,
            recommended_decision="keep",
            summary="No changes detected — all data remains valid.",
        )

    if policy is not None:
        return _classify_with_policy(diff, policy)

    return _classify_with_default_rules(diff)
