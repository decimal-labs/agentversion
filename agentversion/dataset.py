"""Dataset models for the AgentVersion.

Defines canonical schemas for trace-derived objects: tasks, episodes,
steps, and dataset snapshots.

See spec/reference.md §2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentversion._shared import Message
from agentversion.constants import SPEC_VERSION

# --- 2.1 Task (§2.1) ---


class TaskSource(BaseModel):
    """Where this task came from."""

    type: str  # e.g. "production", "synthetic", "manual"
    system: str | None = None
    external_id: str | None = None


class TaskInput(BaseModel):
    """Input for a task (supports multi-turn)."""

    messages: list[Message]


class Task(BaseModel):
    """A task object representing a unit of work for an agent.

    See spec/reference.md §2.1.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["task"] = "task"
    task_id: str
    source: TaskSource | None = None
    created_at: datetime
    input: TaskInput
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


# --- 2.2 Episode (§2.2) ---


class EpisodeSource(BaseModel):
    """Where this episode came from."""

    type: str  # e.g. "production_trace", "replay", "synthetic"
    system: str | None = None
    external_trace_id: str | None = None


class EpisodeResult(BaseModel):
    """Result of an episode execution."""

    final_output: dict[str, Any] | None = None
    success_label: bool | None = None


class EpisodeLineage(BaseModel):
    """Lineage tracking for an episode."""

    parent_episode_id: str | None = None
    derived_from: str | None = None  # "original", "replay", "repair"


class ObservabilityRefs(BaseModel):
    """References to observability systems."""

    otel_trace_id: str | None = None
    otel_span_id: str | None = None
    source_url: str | None = None


class Episode(BaseModel):
    """An episode representing one execution attempt of a task.

    See spec/reference.md §2.2.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["episode"] = "episode"
    episode_id: str
    task_id: str
    source: EpisodeSource | None = None
    manifest_id: str | None = None
    status: Literal["success", "failure", "error", "timeout", "cancelled"]
    started_at: datetime | None = None
    ended_at: datetime | None = None
    step_ids: list[str] = Field(default_factory=list)
    result: EpisodeResult | None = None
    lineage: EpisodeLineage | None = None
    observability_refs: ObservabilityRefs | None = None


# --- 2.3 Step (§2.3) ---


class StepActor(BaseModel):
    """Who/what performed this step."""

    type: str  # "agent", "tool", "user", "system"
    name: str | None = None


class StepInput(BaseModel):
    """Input to a step."""

    messages: list[Message] | None = None


class ToolCallOutput(BaseModel):
    """A tool call output."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class StepOutput(BaseModel):
    """Output of a step."""

    tool_call: ToolCallOutput | None = None
    text: str | None = None


class SchemaRefs(BaseModel):
    """References to schemas used in this step."""

    tool_input_schema_hash: str | None = None
    tool_output_schema_hash: str | None = None


class TokenUsage(BaseModel):
    """Token usage statistics."""

    input_tokens: int | None = None
    output_tokens: int | None = None


STEP_TYPES = [
    "llm_call",
    "tool_call",
    "router_decision",
    "subagent_handoff",
    "validator_check",
    "memory_read",
    "memory_write",
    "retrieval",
    "system_event",
]


class Step(BaseModel):
    """An atomic step within an episode.

    See spec/reference.md §2.3.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["step"] = "step"
    step_id: str
    episode_id: str
    index: int
    step_type: str  # one of STEP_TYPES
    started_at: datetime | None = None
    ended_at: datetime | None = None
    actor: StepActor | None = None
    input: StepInput | None = None
    output: StepOutput | None = None
    schema_refs: SchemaRefs | None = None
    observability_refs: ObservabilityRefs | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- 2.4 Dataset Snapshot (§2.4) ---


class DataClassification(BaseModel):
    """Compliance labels on a dataset snapshot (§3n).

    Used for filtering ("show me datasets I can ship outside the EU"),
    retention enforcement, and consent tracking.
    """

    pii_state: Literal["raw", "redacted", "synthetic", "none"] = "none"
    retention_days: int | None = Field(None, ge=1)
    residency: list[str] = Field(default_factory=list)  # e.g. ["us-east-1", "eu-west-1"]
    redaction_policy_ref: str | None = None
    consent_basis: Literal["consent", "contract", "legitimate_interest", "legal_obligation", "vital_interest", "public_task"] | None = None


class SelectionPolicy(BaseModel):
    """How items were selected for this snapshot."""

    source_types: list[str] = Field(default_factory=list)
    required_episode_status: str | None = None
    required_policy_compliance: bool | None = None
    pii_states: list[Literal["raw", "redacted", "synthetic", "none"]] = Field(
        default_factory=list,
        description=(
            "Filter: episodes whose data_classification.pii_state is in this list "
            "are eligible. Empty list = no filter."
        ),
    )


class ItemRef(BaseModel):
    """Reference to a specific task/episode/step combination."""

    task_id: str
    episode_id: str | None = None
    step_id: str | None = None


class SnapshotLineage(BaseModel):
    """Lineage tracking for a dataset snapshot."""

    source_snapshot_ids: list[str] = Field(default_factory=list)
    built_from_manifest_ids: list[str] = Field(default_factory=list)


class DatasetSnapshot(BaseModel):
    """A curated frozen dataset snapshot with provenance.

    See spec/reference.md §2.4.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["dataset_snapshot"] = "dataset_snapshot"
    snapshot_id: str
    name: str
    dataset_type: str  # e.g. "sft", "eval", "preference"
    created_at: datetime
    selection_policy: SelectionPolicy | None = None
    item_refs: list[ItemRef] = Field(default_factory=list)
    lineage: SnapshotLineage | None = None
    data_classification: DataClassification | None = None
