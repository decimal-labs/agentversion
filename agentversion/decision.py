"""Compatibility decision models for the AgentVersion.

Defines per-episode compatibility classification (keep / repair / replay / drop)
and batch operations for platform-scale classification.

See spec/reference.md §3 and §12.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agentversion.constants import SPEC_VERSION

# --- Compatibility Decision (§3) ---


class DecisionSubject(BaseModel):
    """What this compatibility decision applies to."""

    type: Literal["task", "episode", "step", "dataset_item"]
    id: str


class RepairPlan(BaseModel):
    """Plan for repairing data without full replay."""

    strategy: Literal["rename_field", "remove_field", "convert_format", "schema_migration", "custom"] | None = None
    transform_refs: list[str] = Field(default_factory=list)


class ReplayPlan(BaseModel):
    """Plan for replaying an episode."""

    replayability: Literal["fully_replayable", "partially_replayable", "not_replayable"] | None = None
    required_context: list[str] = Field(default_factory=list)


class DecisionDetails(BaseModel):
    """Supporting details for a compatibility decision."""

    summary: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


# Allowed reason codes (§3)
REASON_CODES = [
    "tool_missing",
    "tool_schema_incompatible",
    "tool_semantics_changed",
    "skill_missing",
    "skill_content_changed",
    "prompt_policy_changed",
    "prompt_format_changed",
    "model_runtime_changed",
    "workflow_surface_changed",
    "subagent_interface_changed",
    "output_contract_changed",
    "guardrail_policy_changed",
    "behavioral_policy_changed",
    "context_config_changed",
    "region_changed",
    "infra_image_changed",
    "external_service_pin_changed",
    "runtime_version_changed",
    "environment_unreplayable",
    "missing_artifacts",
    "insufficient_confidence",
]


class CompatibilityDecision(BaseModel):
    """Per-episode compatibility classification.

    See spec/reference.md §3.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["compatibility_decision"] = "compatibility_decision"
    decision_id: str
    subject: DecisionSubject
    old_manifest_id: str
    target_manifest_id: str
    decision: Literal["keep", "repair", "replay", "drop"]
    reason_codes: list[str] = Field(default_factory=list)
    details: DecisionDetails | None = None
    repair_plan: RepairPlan | None = None
    replay_plan: ReplayPlan | None = None
    created_at: datetime

    @field_validator("reason_codes")
    @classmethod
    def _validate_reason_codes(cls, v: list[str]) -> list[str]:
        """Reason codes must come from the canonical ``REASON_CODES`` vocabulary.

        The JSON Schema enforces this enum on the wire; mirroring it on the model
        keeps the schema and the Python type in agreement, so a decision can't be
        constructed with a code the schema would later reject.
        """
        unknown = [c for c in v if c not in REASON_CODES]
        if unknown:
            raise ValueError(
                f"Unknown reason_codes: {unknown}. Valid codes: {REASON_CODES}"
            )
        return v


# --- Compatibility Batch Condition DSL (§12) ---
#
# This is a *descriptive* controlled vocabulary, not an executable rule engine.
# Condition strings on a ClassificationRule are validated for well-formedness
# (see validate_condition) but are NOT evaluated by this library: a
# CompatibilityBatch records classifications produced elsewhere, and the
# condition documents *which* rule grouped a set of episodes.
#
# These predicate tokens are intentionally a different vocabulary from the
# REASON_CODES above. Tokens describe *what the diff looked like* (inputs to a
# decision); reason codes *explain a decision* (its outputs). They are not
# expected to match one-to-one.

# Predefined condition tokens for classification rules.
# Surface-level state tokens:
SURFACE_STATE_TOKENS = frozenset({
    "tool_surface_unchanged",
    "tool_surface_changed",
    "skill_surface_unchanged",
    "skill_surface_changed",
    "prompt_surface_unchanged",
    "prompt_surface_changed",
    "model_surface_unchanged",
    "model_surface_changed",
    "workflow_surface_unchanged",
    "workflow_surface_changed",
    "subagent_surface_unchanged",
    "subagent_surface_changed",
    "output_surface_unchanged",
    "output_surface_changed",
    "guardrail_surface_unchanged",
    "guardrail_surface_changed",
    "context_surface_unchanged",
    "context_surface_changed",
    "environment_surface_unchanged",
    "environment_surface_changed",
})

# Parameterized condition tokens (use with colon, e.g. "tool_missing:search_population"):
PARAMETERIZED_TOKENS = frozenset({
    "tool_missing",
    "tool_schema_changed",
    "episode_uses_tool",
    "episode_uses_format",
})

# Special condition tokens:
SPECIAL_TOKENS = frozenset({
    "output_contract_changed",
    "model_changed",
    "prompt_changed",
    "workflow_changed",
    "environment_unreplayable",
    "all_surfaces_unchanged",
})

# Logical operators
LOGICAL_OPERATORS = frozenset({"AND", "OR"})

# All valid bare tokens (non-parameterized)
ALL_CONDITION_TOKENS = SURFACE_STATE_TOKENS | SPECIAL_TOKENS


def validate_condition(condition: str) -> bool:
    """Validate that a condition string uses only predefined tokens.

    Checks *well-formedness* only — that every token is recognized. It does NOT
    evaluate the condition against a diff or episode; conditions are descriptive
    metadata on a recorded classification (see the Condition DSL note above).

    Valid conditions consist of predefined tokens joined by AND / OR operators.
    Parameterized tokens use colon syntax: ``tool_missing:search_population``.

    Examples:
        - ``"tool_surface_unchanged AND prompt_surface_unchanged"``
        - ``"tool_missing:search_population"``
        - ``"output_contract_changed AND episode_uses_format:json"``

    Returns:
        True if the condition is valid.

    Raises:
        ValueError: If the condition contains unknown tokens.
    """
    parts = condition.split()
    for part in parts:
        if part in LOGICAL_OPERATORS:
            continue
        # Check for parameterized token (e.g. "tool_missing:search_population")
        if ":" in part:
            token, _param = part.split(":", 1)
            if token not in PARAMETERIZED_TOKENS:
                raise ValueError(
                    f"Unknown parameterized condition token: {token!r}. "
                    f"Valid tokens: {sorted(PARAMETERIZED_TOKENS)}"
                )
            continue
        if part not in ALL_CONDITION_TOKENS:
            raise ValueError(
                f"Unknown condition token: {part!r}. "
                f"Valid tokens: {sorted(ALL_CONDITION_TOKENS)} "
                f"or parameterized: {sorted(PARAMETERIZED_TOKENS)}"
            )
    return True


# --- Compatibility Batch (§12) ---


class ClassificationRule(BaseModel):
    """A rule that classified a group of episodes.

    The ``condition`` is a descriptive record of *why* this group was classified
    the way it was. It is validated against the predefined token vocabulary
    (see ``validate_condition``) but is not evaluated by this library.
    """

    rule_id: str
    condition: str
    decision: Literal["keep", "repair", "replay", "drop"]
    reason_codes: list[str] = Field(default_factory=list)
    repair_strategy: Literal["rename_field", "remove_field", "convert_format", "schema_migration", "custom"] | None = None
    matched_count: int

    @field_validator("condition")
    @classmethod
    def _validate_condition(cls, v: str) -> str:
        validate_condition(v)
        return v


class CompatibilityBatchSummary(BaseModel):
    """Headline counts for a batch classification."""

    total_episodes: int
    keep: int
    repair: int
    replay: int
    drop: int


class CompatibilityBatch(BaseModel):
    """Batch classification for platform-scale compatibility decisions.

    See spec/reference.md §12.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["compatibility_batch"] = "compatibility_batch"
    batch_id: str
    old_manifest_id: str
    target_manifest_id: str
    diff_ref: str | None = None
    created_at: datetime
    summary: CompatibilityBatchSummary
    classification_rules: list[ClassificationRule]
    episode_decisions_ref: str | None = None
