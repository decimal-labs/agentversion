"""Replay job and result models for the AgentVersion.

Defines replay job input, constraints, results, and comparison.

See spec/reference.md §4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from agentversion._shared import Message  # re-exported below for back-compat
from agentversion.constants import SPEC_VERSION

# --- Determinism (§3f) ---


class DeterminismHints(BaseModel):
    """Optional knobs to make a replay reproducible.

    ``random_seed`` is passed to the sampler so temperature-affected outputs
    converge to the original trace. ``clock_freeze_at`` substitutes for the
    agent's notion of "now". ``tool_response_pinning_ref`` is a URI (see
    :mod:`agentversion.refs`) pointing at a JSONL of recorded tool
    responses; the replay runner returns those instead of calling tools live.
    """

    random_seed: int | None = None
    clock_freeze_at: datetime | None = None
    tool_response_pinning_ref: str | None = None


__all__ = [
    "Attachment",
    "ComparisonSummary",
    "Message",
    "ReplayConstraints",
    "ReplayInput",
    "ReplayJob",
    "ReplayLineage",
    "ReplayResult",
    "RequestedOutputs",
    "RuntimeMetadata",
]


class Attachment(BaseModel):
    """An attachment referenced in a replay."""

    attachment_id: str
    uri: str | None = None
    mime_type: str | None = None


# --- Replay Job (§4) ---


class ReplayInput(BaseModel):
    """Input data for a replay job."""

    messages: list[Message]
    conversation_history: list[Message] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    determinism: DeterminismHints | None = None


class ReplayConstraints(BaseModel):
    """Resource constraints for replay execution."""

    timeout_seconds: int | None = Field(None, ge=1)
    max_cost_usd: float | None = Field(None, ge=0)
    allow_network: bool | None = None


class RequestedOutputs(BaseModel):
    """What outputs to include from the replay."""

    include_full_trace: bool = True
    include_step_artifacts: bool = True
    include_final_output: bool = True


class ReplayLineage(BaseModel):
    """Lineage tracking for the replay."""

    requested_from_episode_id: str | None = None


class ReplayJob(BaseModel):
    """Replay job definition.

    See spec/reference.md §4.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["replay_job"] = "replay_job"
    replay_job_id: str
    task_id: str
    source_episode_id: str | None = None
    target_manifest_id: str
    mode: Literal["customer_runtime", "offline_batch", "analysis_only"]
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    replay_input: ReplayInput
    constraints: ReplayConstraints | None = None
    requested_outputs: RequestedOutputs | None = None
    lineage: ReplayLineage | None = None
    created_at: datetime


# --- Replay Result (§4) ---


class ToolPathDiff(BaseModel):
    """Structural diff of the tool-call sequence between original and replay (§3m)."""

    steps_added: list[str] = Field(default_factory=list)
    steps_removed: list[str] = Field(default_factory=list)
    first_divergence_step_index: int | None = None


class ComparisonSummary(BaseModel):
    """Summary of differences between original and replayed episode.

    Booleans answer "did this change?"; deltas answer "by how much?". An
    analytics pipeline can sort divergent replays by ``final_output_diff_pct``
    or ``eval_score_delta`` to surface the worst regressions first.
    """

    final_output_changed: bool | None = None
    final_output_diff_pct: float | None = Field(None, ge=0.0, le=100.0)
    tool_path_changed: bool | None = None
    tool_path_diff: ToolPathDiff | None = None
    output_contract_valid: bool | None = None
    step_count_delta: int | None = None
    latency_delta_ms: int | None = None
    cost_delta_usd: float | None = None
    eval_score_delta: float | None = None


class RuntimeMetadata(BaseModel):
    """Metadata about the replay executor."""

    executor_type: str | None = None
    executor_version: str | None = None


class ReplayResult(BaseModel):
    """Result of a replay job execution.

    See spec/reference.md §4.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["replay_result"] = "replay_result"
    replay_job_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    target_manifest_id: str
    replayed_episode_id: str | None = None
    replayability: Literal["fully_replayable", "partially_replayable", "not_replayable"] | None = None
    runtime_metadata: RuntimeMetadata | None = None
    comparison_summary: ComparisonSummary | None = None
    completed_at: datetime | None = None
