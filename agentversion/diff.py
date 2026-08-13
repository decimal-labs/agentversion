"""Diff engine for AgentVersion.

Computes surface-level diffs between two manifests, classifying each
changed surface with granular severity levels (minor / moderate / major)
and breaking / non-breaking type.

See spec/reference.md §5 for the diff format.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentversion.constants import SPEC_VERSION
from agentversion.hasher import hash_surface, prepare_surface_for_hashing

# --- Pydantic models for serializable diff output ---


class SurfaceChange(BaseModel):
    """A single surface-level change between two manifests."""

    surface: str
    change_type: Literal["breaking", "non_breaking"]
    severity: Literal["minor", "moderate", "major"] = "minor"
    details: list[str] = Field(default_factory=list)


class DiffSummary(BaseModel):
    """Headline counts for the diff."""

    breaking_surfaces: int = 0
    non_breaking_surfaces: int = 0
    max_severity: Literal["none", "minor", "moderate", "major"] = "none"


class ManifestDiff(BaseModel):
    """Full diff result between two manifests.

    See spec/reference.md §5.
    """

    spec_version: str = SPEC_VERSION
    kind: Literal["manifest_diff"] = "manifest_diff"
    old_manifest_id: str
    new_manifest_id: str
    changed_surfaces: list[SurfaceChange] = Field(default_factory=list)
    summary: DiffSummary = Field(default_factory=DiffSummary)


# --- Breaking-change classification rules ---

# ── Severity types ──────────────────────────────────────

Severity = Literal["minor", "moderate", "major"]
_SEVERITY_ORDER = {"minor": 1, "moderate": 2, "major": 3}


def _max_severity(*levels: Severity) -> Severity:
    """Return the highest severity from a set of levels."""
    if not levels:
        return "minor"
    return max(levels, key=lambda s: _SEVERITY_ORDER.get(s, 0))


# ── Per-surface severity classifiers ────────────────────


def prompt_severity(old_text: str, new_text: str) -> tuple[Severity, float]:
    """Classify prompt change severity using text diff ratio.

    Returns (severity, diff_pct) where diff_pct is 0-100.
    Thresholds (per spec/compatibility-policy.md): ≤5% → minor, 5-30% → moderate, >30% → major.

    NOTE: This is a standalone helper for callers that have the inline prompt
    text on hand. ``diff_manifests`` / ``_adapt_prompt_stack`` classify prompt
    changes from hashes/versions alone (no inline text), so they do NOT call
    this — the ratio tiers here are not part of the manifest diff pipeline.
    """
    if not old_text and not new_text:
        return "minor", 0.0
    ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()
    diff_pct = round((1 - ratio) * 100, 1)
    if diff_pct <= 5:
        return "minor", diff_pct
    elif diff_pct <= 30:
        return "moderate", diff_pct
    else:
        return "major", diff_pct


def model_severity(
    old: dict[str, Any], new: dict[str, Any]
) -> tuple[Severity, list[str]]:
    """Classify model_runtime change severity.

    - Same model, config tweak (temp/top_p) → minor
    - Version bump within same family → moderate
    - Provider or family change → major
    """
    details: list[str] = []
    severity: Severity = "minor"

    old_provider = str(old.get("provider", "")).lower()
    new_provider = str(new.get("provider", "")).lower()
    old_model = str(old.get("model", ""))
    new_model = str(new.get("model", ""))

    if old_provider != new_provider:
        details.append(f"provider: {old_provider!r} → {new_provider!r}")
        severity = "major"
    elif old_model != new_model:
        # Check if same family (e.g. gpt-4o vs gpt-4o-mini)
        old_family = _extract_model_family(old_model)
        new_family = _extract_model_family(new_model)
        if old_family != new_family:
            details.append(f"model family: {old_family!r} → {new_family!r}")
            severity = "major"
        else:
            details.append(f"model version: {old_model!r} → {new_model!r}")
            severity = "moderate"

    # tool_calling_mode lives at the top level of model_runtime.
    if old.get("tool_calling_mode") != new.get("tool_calling_mode"):
        details.append(
            f"tool_calling_mode: {old.get('tool_calling_mode')!r} → {new.get('tool_calling_mode')!r}"
        )
        severity = _max_severity(severity, "moderate")

    # Generation params are nested under generation_config (not top-level).
    old_gc = old.get("generation_config") or {}
    new_gc = new.get("generation_config") or {}
    for key in ("temperature", "top_p", "max_tokens", "response_format"):
        if old_gc.get(key) != new_gc.get(key):
            details.append(f"{key}: {old_gc.get(key)!r} → {new_gc.get(key)!r}")

    for key in ("runtime_version", "model_config_hash"):
        if old.get(key) != new.get(key):
            details.append(f"{key}: {old.get(key)!r} → {new.get(key)!r}")

    old_env = old.get("envelope") or {}
    new_env = new.get("envelope") or {}
    if old_env != new_env:
        env_severity = _envelope_severity(old_env, new_env, details)
        severity = _max_severity(severity, env_severity)

    if not details:
        details.append("model_runtime changed")

    return severity, details


# Cost/latency change factor at or above which the envelope swap is treated as
# economically significant. A 2x+ shift in per-token cost or expected latency
# means the manifest's "expected economics" commitment (§3h) has materially
# changed even if the model name diff was otherwise minor.
_ENVELOPE_FACTOR_MODERATE = 2.0
_ENVELOPE_FACTOR_MAJOR = 10.0


def _envelope_factor(old_v: Any, new_v: Any) -> float | None:
    """Ratio of change between two numeric envelope values (>= 1.0), or None.

    Returns the larger of new/old and old/new so both a cost *increase* and a
    cost *drop* register the same magnitude. None when either side is missing,
    non-numeric, or zero (no meaningful ratio).
    """
    if not isinstance(old_v, (int, float)) or not isinstance(new_v, (int, float)):
        return None
    if old_v <= 0 or new_v <= 0:
        return None
    return max(new_v / old_v, old_v / new_v)


def _envelope_severity(
    old_env: dict[str, Any], new_env: dict[str, Any], details: list[str]
) -> Severity:
    """Classify a model_runtime envelope change by cost/latency magnitude.

    Honors the ModelEnvelope contract: a swap from a cheap model to an
    expensive one (or a large latency regression) escalates severity even when
    the model name change was otherwise minor.
    """
    severity: Severity = "minor"
    appended = False

    old_cost = old_env.get("cost") or {}
    new_cost = new_env.get("cost") or {}
    cost_keys = (
        "input_per_1k_tokens_usd",
        "output_per_1k_tokens_usd",
        "cached_input_per_1k_tokens_usd",
    )
    latency_keys = ("expected_latency_ms_p50", "expected_latency_ms_p99")

    for key in cost_keys:
        factor = _envelope_factor(old_cost.get(key), new_cost.get(key))
        if factor is None:
            continue
        if factor >= _ENVELOPE_FACTOR_MAJOR:
            severity = _max_severity(severity, "major")
        elif factor >= _ENVELOPE_FACTOR_MODERATE:
            severity = _max_severity(severity, "moderate")
        if factor >= _ENVELOPE_FACTOR_MODERATE:
            details.append(
                f"cost.{key}: {old_cost.get(key)!r} → {new_cost.get(key)!r} "
                f"({factor:.1f}x)"
            )
            appended = True

    for key in latency_keys:
        factor = _envelope_factor(old_env.get(key), new_env.get(key))
        if factor is None:
            continue
        if factor >= _ENVELOPE_FACTOR_MODERATE:
            severity = _max_severity(severity, "moderate")
            details.append(
                f"{key}: {old_env.get(key)!r} → {new_env.get(key)!r} "
                f"({factor:.1f}x)"
            )
            appended = True

    if not appended:
        details.append("envelope changed")

    return severity


# Trailing size/variant/date suffixes that mark a *version* of the same family
# rather than a different family. Dates appear in two shapes: dashed (OpenAI/Google
# `gpt-4o-2024-08-06`) and compact 8-digit (Anthropic `claude-3-5-sonnet-20241022`).
# Both must be stripped, or two date-revs of the same model read as different
# families and a routine model bump is mis-classified as a `major`/`replay`.
_MODEL_SUFFIX_RE = re.compile(r"-(mini|latest|preview|turbo|\d{4}-\d{2}-\d{2}|\d{8})$")


def _extract_model_family(model_name: str) -> str:
    """Extract family from a model name by stripping size/variant/date suffixes.

    Examples: ``gpt-4o-mini`` → ``gpt-4o``; ``claude-3-5-sonnet-20241022`` →
    ``claude-3-5-sonnet``; ``gpt-4o-mini-2024-07-18`` → ``gpt-4o`` (stripped
    iteratively). Distinct families (``gpt-4`` vs ``gpt-4o``) are preserved.
    """
    prev = None
    while prev != model_name:
        prev = model_name
        model_name = _MODEL_SUFFIX_RE.sub("", model_name)
    return model_name


def tool_registry_severity(
    old: dict[str, Any], new: dict[str, Any]
) -> tuple[Severity, Literal["breaking", "non_breaking"], list[str]]:
    """Classify tool_registry changes with granular severity.

    - Tool added → minor (non-breaking)
    - Tool param added (optional) → minor
    - Tool param renamed/type changed → moderate (breaking)
    - Tool removed → major (breaking)
    """
    details: list[str] = []
    severity: Severity = "minor"
    is_breaking = False

    old_tools = {t["name"]: t for t in old.get("tools", [])}
    new_tools = {t["name"]: t for t in new.get("tools", [])}

    removed = set(old_tools) - set(new_tools)
    added = set(new_tools) - set(old_tools)
    common = set(old_tools) & set(new_tools)

    for name in sorted(removed):
        details.append(f"{name} removed")
        severity = "major"
        is_breaking = True

    for name in sorted(added):
        details.append(f"{name} added")
        # Adding a tool is non-breaking, minor

    for name in sorted(common):
        old_t, new_t = old_tools[name], new_tools[name]
        if old_t == new_t:
            continue

        old_in_hash = old_t.get("input_schema_hash", "")
        new_in_hash = new_t.get("input_schema_hash", "")
        old_out_hash = old_t.get("output_schema_hash", "")
        new_out_hash = new_t.get("output_schema_hash", "")

        schema_changed = (
            old_in_hash != new_in_hash or old_out_hash != new_out_hash
        )

        # §3i: semantic_version bump catches behavioral drift that schemas miss.
        # Major bump is breaking (behavioral change at major version); minor /
        # patch are non-breaking but warrant attention via moderate severity.
        old_sv = old_t.get("semantic_version")
        new_sv = new_t.get("semantic_version")
        sv_bump = _semver_bump_kind(old_sv, new_sv)

        if schema_changed:
            details.append(f"{name} schema changed")
            severity = _max_severity(severity, "moderate")
            is_breaking = True
        elif sv_bump == "major":
            details.append(f"{name} semantic_version major bump: {old_sv} → {new_sv}")
            severity = _max_severity(severity, "moderate")
            is_breaking = True
        elif sv_bump == "minor":
            details.append(f"{name} semantic_version minor bump: {old_sv} → {new_sv}")
            severity = _max_severity(severity, "minor")
        elif sv_bump == "patch":
            details.append(f"{name} semantic_version patch bump: {old_sv} → {new_sv}")
        else:
            details.append(f"{name} modified (non-schema)")

    return severity, ("breaking" if is_breaking else "non_breaking"), details


def _semver_bump_kind(
    old: str | None, new: str | None
) -> Literal["major", "minor", "patch"] | None:
    """Classify the semver bump between two version strings.

    Returns None if either side is missing or unparseable, or if they're equal.
    """
    if not old or not new or old == new:
        return None
    sv_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
    om, nm = sv_re.match(old), sv_re.match(new)
    if not om or not nm:
        return None
    o_major, o_minor, o_patch = (int(x) for x in om.groups())
    n_major, n_minor, n_patch = (int(x) for x in nm.groups())
    if n_major != o_major:
        return "major"
    if n_minor != o_minor:
        return "minor"
    if n_patch != o_patch:
        return "patch"
    return None


def workflow_severity(
    old: dict[str, Any], new: dict[str, Any]
) -> tuple[Severity, list[str]]:
    """Classify workflow changes against the canonical WorkflowContract shape.

    - graph_name change only → minor (rename)
    - graph_version / routing_policy_version change → moderate
    - graph_hash change (topology) → major
    """
    details: list[str] = []
    severity: Severity = "minor"

    if old.get("graph_hash") != new.get("graph_hash"):
        details.append("graph topology changed")
        severity = _max_severity(severity, "major")

    if old.get("routing_policy_version") != new.get("routing_policy_version"):
        details.append(
            f"routing_policy_version: {old.get('routing_policy_version')!r} → "
            f"{new.get('routing_policy_version')!r}"
        )
        severity = _max_severity(severity, "moderate")

    if old.get("graph_version") != new.get("graph_version"):
        details.append(
            f"graph_version: {old.get('graph_version')!r} → {new.get('graph_version')!r}"
        )
        severity = _max_severity(severity, "moderate")

    if old.get("graph_name") != new.get("graph_name"):
        details.append(
            f"graph_name: {old.get('graph_name')!r} → {new.get('graph_name')!r}"
        )

    if not details:
        details.append("workflow changed")

    return severity, details


def subagent_severity(
    old: Any, new: Any
) -> tuple[Severity, list[str]]:
    """Classify subagent changes.

    - Config tweak → minor
    - Subagent added → moderate
    - Subagent manifest_ref changed → moderate
    - Subagent removed/replaced → major

    Handles both dict format ({"agents": [...]}) and raw list format ([...]).
    """
    details: list[str] = []
    severity: Severity = "minor"

    def _agent_key(a: dict[str, Any]) -> str:
        """Identity key for a subagent: its name, or a stable content hash when
        unnamed — so reordering or removing an unnamed subagent reads as an
        add/remove of that subagent, not a positional rename."""
        name = a.get("name")
        return name if name else f"unnamed:{hash_surface(a)}"

    def _extract_agents(data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return {_agent_key(a): a for a in data if isinstance(a, dict)}
        if isinstance(data, dict):
            agents_list = data.get("agents", data.get("subagents", []))
            if isinstance(agents_list, list):
                return {_agent_key(a): a for a in agents_list if isinstance(a, dict)}
        return {}

    old_agents = _extract_agents(old)
    new_agents = _extract_agents(new)

    removed = set(old_agents) - set(new_agents)
    added = set(new_agents) - set(old_agents)
    common = set(old_agents) & set(new_agents)

    if removed:
        details.append(f"subagents removed: {sorted(str(n) for n in removed)}")
        severity = "major"
    if added:
        details.append(f"subagents added: {sorted(str(n) for n in added)}")
        severity = _max_severity(severity, "moderate")

    # Check for manifest_ref / hash / contents changes in common subagents
    for name in sorted(common):
        old_a, new_a = old_agents[name], new_agents[name]
        old_ref = old_a.get("manifest_ref")
        new_ref = new_a.get("manifest_ref")
        if old_ref != new_ref:
            details.append(f"{name} manifest_ref changed: {old_ref!r} → {new_ref!r}")
            severity = _max_severity(severity, "moderate")
        elif old_a.get("hash") != new_a.get("hash"):
            details.append(f"{name} hash changed")
            severity = _max_severity(severity, "moderate")
        elif hash_surface(old_a) != hash_surface(new_a):
            # Some other field (e.g. handoff_schema_hash) changed.
            # Use canonical-hash parity so benign key reshapes don't fire.
            details.append(f"{name} contents changed")
            severity = _max_severity(severity, "minor")

    return severity, details


def output_contract_severity(
    old: dict[str, Any], new: dict[str, Any]
) -> tuple[Severity, list[str]]:
    """Classify output_contract changes (per spec/compatibility-policy.md §tiers).

    - Format change → minor
    - Schema change → moderate
    - Strict-mode toggle → major (a strict flip newly *rejects* previously-valid
      outputs, so it is the most consumer-breaking change to the contract)
    """
    details: list[str] = []
    severity: Severity = "minor"

    if old.get("format") != new.get("format"):
        details.append(f"format: {old.get('format')!r} → {new.get('format')!r}")
        severity = _max_severity(severity, "minor")

    if old.get("schema_hash") != new.get("schema_hash"):
        details.append("output schema changed")
        severity = _max_severity(severity, "moderate")

    if old.get("strict") != new.get("strict"):
        details.append(f"strict: {old.get('strict')} → {new.get('strict')}")
        severity = _max_severity(severity, "major")

    return severity, details


def skill_registry_severity(
    old: dict[str, Any], new: dict[str, Any]
) -> tuple[Severity, Literal["breaking", "non_breaking"], list[str]]:
    """Classify skill_registry changes with granular severity.

    - Skill added → minor (non-breaking)
    - Skill content hash changed → moderate (non-breaking)
    - Skill removed → moderate (breaking)
    - Selection strategy changed → moderate (breaking)
    """
    details: list[str] = []
    severity: Severity = "minor"
    is_breaking = False

    old_skills = {s["name"]: s for s in old.get("skills", [])}
    new_skills = {s["name"]: s for s in new.get("skills", [])}

    removed = set(old_skills) - set(new_skills)
    added = set(new_skills) - set(old_skills)
    common = set(old_skills) & set(new_skills)

    for name in sorted(removed):
        details.append(f"{name} removed")
        severity = _max_severity(severity, "moderate")
        is_breaking = True

    for name in sorted(added):
        details.append(f"{name} added")
        # Adding a skill is non-breaking, minor

    for name in sorted(common):
        old_s, new_s = old_skills[name], new_skills[name]
        if old_s == new_s:
            continue

        if old_s.get("hash", "") != new_s.get("hash", ""):
            details.append(f"{name} content changed")
            severity = _max_severity(severity, "moderate")
            # Content change is non-breaking — it modifies future behavior
            # but doesn't invalidate past traces
        else:
            details.append(f"{name} metadata changed")

    # Selection strategy change
    old_strategy = old.get("selection_strategy")
    new_strategy = new.get("selection_strategy")
    if old_strategy != new_strategy:
        details.append(f"selection_strategy: {old_strategy!r} → {new_strategy!r}")
        severity = _max_severity(severity, "moderate")
        is_breaking = True

    return severity, ("breaking" if is_breaking else "non_breaking"), details


def environment_severity(
    old: dict[str, Any], new: dict[str, Any]
) -> tuple[Severity, list[str]]:
    """Classify environment surface changes.

    Field-level severity:
      - ``deployment_id`` change → minor (rename / blue-green swap)
      - ``region`` change → moderate (data residency, network latency)
      - ``infra_image_hash`` change → moderate (different runtime, tool impls)
      - ``runtime_versions`` change → moderate (e.g. python 3.10 → 3.12)
      - ``external_service_pins`` change → moderate (downstream API drift)
      - ``secret_refs`` change → minor (rotated; same logical secret)
      - ``feature_flags`` change → minor (behavior tuning)
      - ``resource_limits`` change → minor (perf, not correctness)
    """
    details: list[str] = []
    severity: Severity = "minor"

    def _diff_scalar(field: str, sev: Severity) -> None:
        nonlocal severity
        ov, nv = old.get(field), new.get(field)
        if ov != nv:
            details.append(f"{field}: {ov!r} → {nv!r}")
            severity = _max_severity(severity, sev)

    _diff_scalar("deployment_id", "minor")
    _diff_scalar("region", "moderate")
    _diff_scalar("infra_image_hash", "moderate")

    old_rv = old.get("runtime_versions") or {}
    new_rv = new.get("runtime_versions") or {}
    if old_rv != new_rv:
        added = set(new_rv) - set(old_rv)
        removed = set(old_rv) - set(new_rv)
        changed = {k for k in old_rv if k in new_rv and old_rv[k] != new_rv[k]}
        if added or removed or changed:
            parts = []
            if changed:
                parts.append("changed=" + ",".join(sorted(changed)))
            if added:
                parts.append("added=" + ",".join(sorted(added)))
            if removed:
                parts.append("removed=" + ",".join(sorted(removed)))
            details.append("runtime_versions " + " ".join(parts))
            severity = _max_severity(severity, "moderate")

    old_esp = old.get("external_service_pins") or {}
    new_esp = new.get("external_service_pins") or {}
    if old_esp != new_esp:
        details.append("external_service_pins changed")
        severity = _max_severity(severity, "moderate")

    old_sr = set(old.get("secret_refs") or [])
    new_sr = set(new.get("secret_refs") or [])
    if old_sr != new_sr:
        details.append(
            f"secret_refs: added={sorted(new_sr - old_sr)} removed={sorted(old_sr - new_sr)}"
        )
        # minor — rotations and renames don't invalidate traces

    old_ff = old.get("feature_flags") or {}
    new_ff = new.get("feature_flags") or {}
    if old_ff != new_ff:
        details.append("feature_flags changed")
        # minor

    old_rl = old.get("resource_limits") or {}
    new_rl = new.get("resource_limits") or {}
    if old_rl != new_rl:
        details.append("resource_limits changed")
        # minor — perf envelope only

    if not details:
        details.append("environment changed")

    return severity, details


# ── Surface adapters: bridge from severity classifiers to the diff API ──

# Surfaces where ANY change is considered breaking by default (used by the
# generic adapter for surfaces with no dedicated classifier).
_ALWAYS_BREAKING_SURFACES = frozenset({
    "tool_registry",
    "workflow",
    "subagents",
})

# Fields within model_runtime that are breaking if changed.
_BREAKING_MODEL_FIELDS = frozenset({
    "provider",
    "model",
    "tool_calling_mode",
})


# Each adapter returns (change_type, severity, details). Adapters are thin
# wrappers around the public *_severity classifiers — the severity functions
# stay independent so they're easy to test in isolation.
SurfaceAdapter = Any  # callable: (old, new) -> tuple[change_type, severity, details]


def _adapt_prompt_stack(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    details: list[str] = []
    severity: Severity = "minor"

    for field in ("system_prompt", "developer_prompt"):
        o = old.get(field) or {}
        n = new.get(field) or {}
        o_hash = o.get("hash") if isinstance(o, dict) else None
        n_hash = n.get("hash") if isinstance(n, dict) else None
        if o_hash != n_hash:
            details.append(f"{field} hash changed")
            severity = _max_severity(severity, "moderate")
        else:
            o_ver = o.get("version") if isinstance(o, dict) else None
            n_ver = n.get("version") if isinstance(n, dict) else None
            if o_ver != n_ver:
                details.append(f"{field} version: {o_ver!r} → {n_ver!r}")

    if old.get("reasoning_policy") != new.get("reasoning_policy"):
        details.append(
            f"reasoning_policy: {old.get('reasoning_policy')!r} → {new.get('reasoning_policy')!r}"
        )
        severity = _max_severity(severity, "moderate")

    for field in ("prompt_assembly_version", "scratchpad_format_version"):
        if old.get(field) != new.get(field):
            details.append(f"{field}: {old.get(field)!r} → {new.get(field)!r}")

    if not details:
        details.append("prompt_stack changed")

    # Prompt changes affect future behavior but don't invalidate past traces.
    return "non_breaking", severity, details


def _adapt_model_runtime(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    sev, details = model_severity(old, new)
    is_breaking = any(old.get(k) != new.get(k) for k in _BREAKING_MODEL_FIELDS)
    return ("breaking" if is_breaking else "non_breaking"), sev, details


def _adapt_tool_registry(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    sev, change_type, details = tool_registry_severity(old, new)
    return change_type, sev, details


def _adapt_skill_registry(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    sev, change_type, details = skill_registry_severity(old, new)
    return change_type, sev, details


def _adapt_workflow(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    sev, details = workflow_severity(old, new)
    return "breaking", sev, details


def _adapt_subagents(old: Any, new: Any) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    # Any subagent change is conservatively breaking (subagents is in
    # _ALWAYS_BREAKING_SURFACES): a subagent is a whole nested agent, and even a
    # version-label relabel is a meaningful identity signal we don't downgrade.
    sev, details = subagent_severity(old, new)
    return "breaking", sev, details


def _adapt_output_contract(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    sev, details = output_contract_severity(old, new)
    is_breaking = (
        old.get("format") != new.get("format")
        or old.get("schema_hash") != new.get("schema_hash")
        or old.get("strict") != new.get("strict")
    )
    return ("breaking" if is_breaking else "non_breaking"), sev, details


def _adapt_environment(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    sev, details = environment_severity(old, new)
    # Environment changes don't invalidate past trace data outright —
    # they affect *replay* semantics. Classify as non-breaking; replay
    # logic uses environment_unreplayable when it can't recreate the env.
    return "non_breaking", sev, details


_BEHAVIORAL_POLICY_RULE_FIELDS = (
    "policy_hash", "objection_threshold", "concede_events", "always_forbidden",
)


def _adapt_behavioral_policy(old: dict[str, Any], new: dict[str, Any]) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    """A change to the bound behavioral policy RULES is BREAKING: it invalidates any eval set and any
    past traces graded under the old policy. (A bare metadata change with an unchanged ``policy_hash``
    is not a rule change.)

    Add/remove are asymmetric and handled here so the surface is severitied by its own
    logic in both directions: *introducing* a policy where there was none is additive
    (non-breaking) — past traces were graded with no policy and stay valid — while
    *removing* a policy is breaking, because past data was graded under rules that no
    longer hold."""
    old = old or {}
    new = new or {}
    if not old and new:
        return "non_breaking", "moderate", ["behavioral_policy introduced"]
    if old and not new:
        return "breaking", "major", ["behavioral_policy removed"]
    o_hash, n_hash = old.get("policy_hash"), new.get("policy_hash")
    if o_hash is not None and n_hash is not None and o_hash == n_hash:
        # Identical policy by its canonical hash → only metadata (e.g. policy_id) differs.
        return "non_breaking", "minor", ["behavioral_policy metadata changed (policy unchanged)"]

    details: list[str] = []
    for field in _BEHAVIORAL_POLICY_RULE_FIELDS:
        if old.get(field) != new.get(field):
            details.append(f"{field}: {old.get(field)!r} → {new.get(field)!r}")
    # Any extra (extra='allow') rule keys beyond the named fields also count as a rule change.
    extra = (set(old) | set(new)) - set(_BEHAVIORAL_POLICY_RULE_FIELDS) - {"policy_id"}
    for k in sorted(extra):
        if old.get(k) != new.get(k):
            details.append(f"{k} changed")
    if not details:
        details.append("behavioral_policy changed")
    return "breaking", "major", details


def _adapt_generic(surface_name: str, old: Any, new: Any) -> tuple[
    Literal["breaking", "non_breaking"], Severity, list[str]
]:
    """Fallback for surfaces without a dedicated severity classifier."""
    is_breaking = surface_name in _ALWAYS_BREAKING_SURFACES
    return (
        "breaking" if is_breaking else "non_breaking",
        "moderate",
        [f"{surface_name} changed"],
    )


_SURFACE_CLASSIFIERS = {
    "prompt_stack": _adapt_prompt_stack,
    "model_runtime": _adapt_model_runtime,
    "tool_registry": _adapt_tool_registry,
    "skill_registry": _adapt_skill_registry,
    "workflow": _adapt_workflow,
    "subagents": _adapt_subagents,
    "output_contract": _adapt_output_contract,
    "environment": _adapt_environment,
    "behavioral_policy": _adapt_behavioral_policy,
}

# All known contract surfaces in canonical order
SURFACE_KEYS = [
    "prompt_stack",
    "model_runtime",
    "tool_registry",
    "skill_registry",
    "workflow",
    "subagents",
    "output_contract",
    "guardrails",
    "context_config",
    "environment",
    "behavioral_policy",
]

# Routing from a producer's flat `component_type` to the contract SURFACE_KEY it lands in,
# including the singular→plural `guardrail`→`guardrails` case. A component type with no entry
# here maps to itself (so a new/custom surface is diffed generically rather than dropped).
COMPONENT_TYPE_TO_SURFACE: dict[str, str] = {
    "tool": "tool_registry",
    "skill": "skill_registry",
    "subagent": "subagents",
    "prompt": "prompt_stack",
    "model": "model_runtime",
    "output_schema": "output_contract",
    "workflow": "workflow",
    "guardrail": "guardrails",
}


def surface_key_for_component(component_type: str) -> str:
    """The contract surface a flat ``component_type`` belongs to (identity for unknown types).

    Looks ``component_type`` up in ``COMPONENT_TYPE_TO_SURFACE`` (for example
    ``guardrail``→``guardrails``) and returns it unchanged when it has no entry.
    """
    return COMPONENT_TYPE_TO_SURFACE.get(component_type, component_type)


def diff_manifests(
    old_data: dict[str, Any],
    new_data: dict[str, Any],
) -> ManifestDiff:
    """Compute a surface-level diff between two manifests.

    Args:
        old_data: The old manifest as a dict.
        new_data: The new manifest as a dict.

    Returns:
        A ``ManifestDiff`` with classified surface changes.
    """
    old_contract = old_data.get("contract", {})
    new_contract = new_data.get("contract", {})

    changes: list[SurfaceChange] = []

    all_surfaces = set(SURFACE_KEYS) | set(old_contract.keys()) | set(new_contract.keys())

    for surface in sorted(all_surfaces):
        old_surface = old_contract.get(surface)
        new_surface = new_contract.get(surface)

        # Skip if both are absent or identical
        if old_surface == new_surface:
            continue

        # Quick-skip identical surfaces. Hash the *prepared* surfaces so this
        # matches identity.overall_hash exactly (model_runtime floats quantized,
        # inline runtime knobs stripped) — otherwise a sub-quantum temperature
        # tweak could hash-equal at the manifest level yet surface as a change.
        if old_surface is not None and new_surface is not None:
            if hash_surface(prepare_surface_for_hashing(surface, old_surface)) == hash_surface(
                prepare_surface_for_hashing(surface, new_surface)
            ):
                continue

        # Classify the change. When one side is absent (a surface was added or
        # removed), route through the dedicated classifier against an empty
        # sentinel so the appearance/removal is severitied by the SAME logic as an
        # in-place change — otherwise diff(A,B) isn't the inverse of diff(B,A)
        # (e.g. an added output_contract{strict:true} would read as a bland
        # "moderate/non_breaking" instead of the major/breaking its classifier
        # assigns). Surfaces with no dedicated classifier fall back to the generic
        # adapter's flat add/remove rule.
        classifier = _SURFACE_CLASSIFIERS.get(surface)
        if classifier:
            empty: Any = [] if surface == "subagents" else {}
            old_input = old_surface if old_surface is not None else empty
            new_input = new_surface if new_surface is not None else empty
            change_type, severity, details = classifier(old_input, new_input)
        else:
            change_type, severity, details = _adapt_generic(
                surface, old_surface, new_surface
            )
            # Surface added or removed (generic surfaces without a classifier)
            if old_surface is None:
                details = [f"{surface} added"]
                severity = "moderate"
            elif new_surface is None:
                details = [f"{surface} removed"]
                change_type = "breaking"
                severity = "major"

        changes.append(
            SurfaceChange(
                surface=surface,
                change_type=change_type,
                severity=severity,
                details=details,
            )
        )

    breaking = sum(1 for c in changes if c.change_type == "breaking")
    non_breaking = sum(1 for c in changes if c.change_type == "non_breaking")
    all_severities = [c.severity for c in changes]
    max_sev = _max_severity(*all_severities) if all_severities else "none"

    return ManifestDiff(
        old_manifest_id=old_data.get("manifest_id", "unknown"),
        new_manifest_id=new_data.get("manifest_id", "unknown"),
        changed_surfaces=changes,
        summary=DiffSummary(
            breaking_surfaces=breaking,
            non_breaking_surfaces=non_breaking,
            max_severity=max_sev,
        ),
    )
