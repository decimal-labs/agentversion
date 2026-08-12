"""Pydantic models for the AgentVersion.

Defines the identity and diffable contract surface of an agent runtime version.
See spec/reference.md §1 and §7 for the full schema.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentversion.constants import SPEC_VERSION

# --- Shared / Leaf Models ---


class CreatedBy(BaseModel):
    """Who created this manifest."""

    type: str
    id: str


class VersionedRef(BaseModel):
    """A versioned reference to a prompt or similar component."""

    id: str
    version: str
    hash: str


class ToolDescriptor(BaseModel):
    """Describes a single tool in the agent's registry.

    The ``input_schema_hash`` and ``output_schema_hash`` fields identify the
    schemas by content hash; ``input_schema_inline`` and ``output_schema_inline``
    optionally embed the full schemas (required for fully-offline replay).
    When inline is present, the validator verifies hash equivalence.

    ``semantic_version`` (§3i) catches *behavioral* drift that schemas can't —
    when a tool's implementation changes but its I/O shape doesn't.
    """

    name: str
    version: str | None = None
    hash: str
    description: str | None = None
    input_schema_hash: str | None = None
    output_schema_hash: str | None = None
    input_schema_inline: dict[str, Any] | None = None
    output_schema_inline: dict[str, Any] | None = None
    stability: Literal["experimental", "stable", "deprecated"] | None = None
    semantic_version: str | None = None  # SemVer "MAJOR.MINOR.PATCH"
    implementation_ref: str | None = None  # commit, image hash, etc.
    annotations: dict[str, Any] | None = None


# --- Contract Surfaces ---


class PromptStack(BaseModel):
    """Prompt surface: system prompt, developer prompt, reasoning policy."""

    system_prompt: VersionedRef | None = None
    developer_prompt: VersionedRef | None = None
    prompt_assembly_version: str | None = None
    scratchpad_format_version: str | None = None
    reasoning_policy: Literal["hidden", "visible", "none"] | None = None


class GenerationConfig(BaseModel):
    """Model generation parameters (temperature, top_p, etc.)."""

    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    response_format: str | None = None


class CostEnvelope(BaseModel):
    """Per-token cost in USD (§3h).

    Costs go into the model_runtime contract because they form a commitment:
    "this manifest is expected to run with these economics." Provider price
    changes warrant a new manifest version.
    """

    input_per_1k_tokens_usd: float | None = Field(None, ge=0)
    output_per_1k_tokens_usd: float | None = Field(None, ge=0)
    cached_input_per_1k_tokens_usd: float | None = Field(None, ge=0)


class RateLimit(BaseModel):
    """Rate-limit envelope the agent expects to run within."""

    rpm: int | None = Field(None, ge=0)  # requests per minute
    tpm: int | None = Field(None, ge=0)  # tokens per minute


class ModelEnvelope(BaseModel):
    """Operational envelope of the model: context window, latency, cost, rate (§3h).

    Anchors ``ReplayConstraints.max_cost_usd`` and similar budget checks. Lets
    the diff classifier flag a swap from a cheap model to an expensive one
    even when the model name change is otherwise minor.
    """

    context_window_tokens: int | None = Field(None, ge=1)
    expected_latency_ms_p50: int | None = Field(None, ge=0)
    expected_latency_ms_p99: int | None = Field(None, ge=0)
    cost: CostEnvelope | None = None
    rate_limit: RateLimit | None = None


class ModelRuntime(BaseModel):
    """Model/runtime surface: provider, model, generation config, envelope."""

    provider: str
    model: str
    model_config_hash: str | None = None
    tool_calling_mode: str | None = None
    runtime_version: str | None = None
    generation_config: GenerationConfig | None = None
    envelope: ModelEnvelope | None = None


class ToolRegistry(BaseModel):
    """Tool surface: all registered tools with hashes."""

    registry_version: str
    registry_hash: str
    tools: list[ToolDescriptor]


class SkillDescriptor(BaseModel):
    """Describes a single skill in the agent's skill catalog.

    Skills are modular, reusable prompt fragments that agents load on demand,
    following the open Agent Skills spec (agentskills.io).  The SDK auto-
    discovers these from SKILL.md files at ``install()`` time.
    """

    name: str
    version: str | None = None
    hash: str  # SHA-256 of the SKILL.md body content
    description: str | None = None
    stability: Literal["experimental", "stable", "deprecated"] | None = None
    tags: list[str] = Field(default_factory=list)
    annotations: dict[str, Any] | None = None


class SkillRegistry(BaseModel):
    """Skill catalog surface: all registered skills with content hashes.

    The registry_hash changes when skills are added, removed, or edited.
    Per-invocation skill *activation* does NOT affect the registry — it
    is recorded as step-level metadata on each trace instead.
    """

    registry_version: str
    registry_hash: str
    selection_strategy: str | None = None  # "llm_semantic", "code_gated", "retrieval_router"
    skills: list[SkillDescriptor]


class WorkflowContract(BaseModel):
    """Workflow surface: graph topology, routing policy."""

    graph_name: str | None = None
    graph_version: str | None = None
    graph_hash: str | None = None
    routing_policy_version: str | None = None


class SubagentDescriptor(BaseModel):
    """Describes a subagent, its handoff schema, and optional manifest reference.

    When ``manifest_ref`` is provided, it points to the sub-agent's own
    AgentManifest (by manifest_id or overall_hash), enabling recursive
    versioning and independent diffing of sub-agent contracts.
    """

    name: str
    version: str
    hash: str
    manifest_ref: str | None = None
    handoff_schema_hash: str | None = None


class OutputContract(BaseModel):
    """Output surface: output schema, format, strictness."""

    version: str
    schema_hash: str
    format: str
    strict: bool = False
    modalities: list[str] = Field(default_factory=list)


class GuardrailBundle(BaseModel):
    """Guardrail surface: guardrail bundle with hash.

    Per-tool concerns like ``requires_confirmation`` live on
    ``ToolDescriptor.annotations`` instead.
    """

    bundle_version: str | None = None
    bundle_hash: str | None = None


class ContextConfig(BaseModel):
    """Context surface: retrieval config, memory policy."""

    retrieval_config_version: str | None = None
    retrieval_config_hash: str | None = None
    memory_policy_version: str | None = None
    context_packing_version: str | None = None


class ResourceLimits(BaseModel):
    """Resource bounds the agent runs under.

    These do not affect correctness but can affect replayability — an episode
    recorded under a 60-second timeout may not replay cleanly under a 5-second
    timeout if the agent makes slow tool calls.
    """

    memory_mb: int | None = None
    cpu_cores: float | None = None
    timeout_seconds: int | None = None
    max_concurrent_calls: int | None = None


class Environment(BaseModel):
    """Environment surface: deployment + infrastructure fingerprint.

    Captures runtime/infrastructure facts that affect execution but aren't
    part of the agent's logical contract (prompts/tools/models/etc).

    Most fields are optional — small agents may only set ``deployment_id``,
    while production deployments will typically pin ``infra_image_hash`` and
    ``external_service_pins`` for reproducibility.

    Security note: ``secret_refs`` holds **names/identifiers** of secrets
    (e.g. ``"prod/openai-api-key"``), never the secret values themselves.
    """

    deployment_id: str | None = None
    region: str | None = None

    infra_image_hash: str | None = None
    runtime_versions: dict[str, str] = Field(default_factory=dict)

    secret_refs: list[str] = Field(default_factory=list)
    external_service_pins: dict[str, str] = Field(default_factory=dict)

    feature_flags: dict[str, Any] = Field(default_factory=dict)

    resource_limits: ResourceLimits | None = None


# --- Top-Level Compound Models ---


class BehavioralPolicy(BaseModel):
    """Versioned BEHAVIORAL-POLICY contract surface.

    Binds the agent to a named policy artifact — the rules it must hold to, e.g. a refund/escalation
    policy ("deny until the customer objects N times, then escalate; never admit liability"), a safety
    guardrail set, or an escalation SOP. The surface is document-agnostic: ``policy_hash`` is the stable
    identity (a hash of whatever policy artifact you bind), and the value carried is opaque to this
    model.

    Why it is a first-class surface: a behavioral policy lives *inside* the prompt, so a prompt-stack
    hash change is classified ``non_breaking`` — yet flipping the policy (a threshold 3 → 1, or removing
    a forbidden rule) INVALIDATES any eval set and any past traces graded under the old policy. Hoisting
    the policy to its own surface makes that flip visible and ``breaking`` instead of silently ``keep``.

    ``policy_hash`` is the identity; the structured rule fields below are OPTIONAL and carried only for
    human-readable diffs (a policy artifact needn't populate any of them — ``extra='allow'`` lets a
    richer or differently-shaped policy spec round-trip without forking this model). They remain on the
    model for backward compatibility with policies already bound this way.
    """

    model_config = ConfigDict(extra="allow")

    policy_id: str | None = None
    policy_hash: str | None = None  # stable hash of the bound policy artifact (the identity)
    # Optional structured rule fields — illustrative, kept for back-compat + human-readable diffs.
    objection_threshold: int | None = None
    concede_events: list[str] | None = None
    always_forbidden: list[str] | None = None


class AgentContract(BaseModel):
    """The diffable contract block containing all surfaces.

    ``extra="allow"`` is the extension hatch: the hasher hashes EVERY contract key, and the diff engine
    diffs any surface present on either side (``diff.SURFACE_KEYS`` ∪ the actual keys). Without retaining
    unknown surfaces, a custom surface (an emerging RAG-corpus / MCP / memory surface, or a vendor
    extension) would be hashed but then DROPPED on ``model_validate`` — so a validate→re-serialize→
    re-hash round-trip would silently change ``overall_hash`` (a moat-breaking non-determinism). Allowing
    extras lets the contract grow without forking the model or breaking hash round-trips.
    """

    model_config = ConfigDict(extra="allow")

    prompt_stack: PromptStack
    model_runtime: ModelRuntime
    tool_registry: ToolRegistry
    skill_registry: SkillRegistry | None = None
    workflow: WorkflowContract
    subagents: list[SubagentDescriptor] | None = Field(default_factory=list)
    output_contract: OutputContract
    guardrails: GuardrailBundle | None = None
    context_config: ContextConfig | None = None
    environment: Environment | None = None
    behavioral_policy: BehavioralPolicy | None = None


class Attestation(BaseModel):
    """A cryptographic attestation over a manifest's canonical hash (§3d).

    SLSA-style. Verification is delegated to implementations; the spec only
    requires that attestations be well-formed and round-trip cleanly.
    """

    signer: str  # e.g. "sigstore:github.com/decimalai/release-pipeline@main"
    algorithm: str  # e.g. "cosign-rsa-sha256", "ssh-ed25519", "x509-rsa-pss-sha256"
    signature: str  # base64-encoded
    signed_payload_hash: str  # the canonical-hash value that was signed
    signed_at: datetime
    key_id: str | None = None
    expires_at: datetime | None = None


class IdentityBlock(BaseModel):
    """Identity: overall hash, algorithm, source commit, build id, attestations."""

    overall_hash: str
    hash_algorithm: str = "jcs-sha256"
    source_commit: str | None = None
    build_id: str | None = None
    yanked_at: datetime | None = None
    yanked_reason: str | None = None
    attestations: list[Attestation] = Field(default_factory=list)


# --- Lifecycle (§3e) ---


LifecycleStage = Literal[
    "draft",
    "candidate",
    "staging",
    "production",
    "deprecated",
    "archived",
]


class LifecycleTransition(BaseModel):
    """One step in a manifest's promotion path.

    Each transition records *who* moved the manifest to a stage, *when*, and
    optionally *what evidence* (eval_ref) and *who approved* it.
    """

    stage: LifecycleStage
    transitioned_at: datetime
    by: str  # actor identifier, e.g. "user:stanley", "system:ci-pipeline"
    eval_ref: str | None = None
    approved_by: list[str] = Field(default_factory=list)
    notes: str | None = None


class Lifecycle(BaseModel):
    """Operational lifecycle of a manifest.

    Not part of ``contract`` — does NOT affect ``identity.overall_hash``. Two
    manifests with identical contracts but different lifecycle states are
    still the same logical version.
    """

    current_stage: LifecycleStage
    history: list[LifecycleTransition] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    sunset_at: datetime | None = None


# --- Evaluation (§3k) ---


class EvalGate(BaseModel):
    """One eval the manifest was scored against.

    ``threshold`` and ``actual_score`` are interpreted by ``threshold_direction``:
    ``"min"`` means actual must be ≥ threshold (the default — higher is better);
    ``"max"`` means actual must be ≤ threshold (lower is better, e.g. latency).
    """

    name: str
    dataset_ref: str | None = None
    threshold: float
    actual_score: float
    threshold_direction: Literal["min", "max"] = "min"
    passed: bool
    ran_at: datetime
    evaluator_ref: str | None = None
    notes: str | None = None


class Evaluation(BaseModel):
    """Eval gates run against this manifest.

    Not part of ``contract`` — does NOT affect ``identity.overall_hash``.
    Evaluation evidence is *about* a manifest, not part of its identity.
    """

    gates: list[EvalGate] = Field(default_factory=list)


class AgentManifest(BaseModel):
    """Top-level Agent Manifest object.

    See spec/reference.md §1 for the full schema definition.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["agent_manifest"] = "agent_manifest"
    manifest_id: str
    agent_name: str
    agent_namespace: str | None = None
    version_label: str
    created_at: datetime
    created_by: CreatedBy | None = None
    parent_manifest_id: str | None = None
    description: str | None = None
    status: Literal["draft", "active", "deprecated", "archived"] | None = None
    tags: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] | None = None
    identity: IdentityBlock
    contract: AgentContract
    lifecycle: Lifecycle | None = None
    evaluation: Evaluation | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)
