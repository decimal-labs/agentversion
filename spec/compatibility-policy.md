# Compatibility Policy

> Status: Stable v1.0 · Added in v0.2.0

Defines **user-configurable rules** that map change severity levels to actions per agent surface.

## Overview

When an agent's manifest changes between versions, the severity classifiers (see [diff.md](diff.md)) determine *how much* each surface changed. The compatibility policy determines *what to do* about each change.

## Schema

JSON Schema: [`schemas/compatibility-policy.schema.json`](../schemas/compatibility-policy.schema.json)

The OSS schema (`additionalProperties: false`) and the `agentversion.compatibility.CompatibilityPolicy` model define the per-surface rule blocks below — including the `behavioral_policy` surface. `source_type_overrides` is **not** part of the OSS schema; it is a [platform-only extension](#platform-only-extensions). A policy that includes `source_type_overrides` will be rejected when validated against the linked OSS schema.

### Structure

```json
{
  "kind": "compatibility_policy",
  "version": "0.1",
  "name": "custom",
  "preset": "default",
  "prompt_stack":      { "on_minor": "keep", "on_moderate": "flag",   "on_major": "drop" },
  "model_runtime":     { "on_minor": "keep", "on_moderate": "flag",   "on_major": "drop" },
  "tool_registry":     { "on_minor": "keep", "on_moderate": "repair", "on_major": "drop" },
  "skill_registry":    { "on_minor": "keep", "on_moderate": "flag",   "on_major": "drop" },
  "behavioral_policy": { "on_minor": "keep", "on_moderate": "flag",   "on_major": "drop" },
  "guardrails":        { "on_minor": "keep", "on_moderate": "flag",   "on_major": "drop" }
}
```

### Actions

| Action | Meaning |
|--------|---------|
| `keep` | Data is still valid — include in datasets |
| `repair` | Data can be fixed — e.g. re-run with updated tool schemas |
| `flag` | Needs human review before inclusion |
| `drop` | Data is incompatible — exclude from datasets |

**Priority**: `drop` > `flag` > `repair` > `keep`. Overall action = worst individual surface action.

### Presets

Each column below is the action taken when that surface changes at the given severity (e.g. "Model major" = action when the `model_runtime` surface changes at **major** severity).

| Preset | Philosophy | Prompt minor | Model major | Tool major |
|--------|-----------|---------------|---------------|-------------|
| `strict` | Flag/drop early | flag | drop | drop |
| `default` | Balanced | keep | drop | drop |
| `permissive` | Keep more data | keep | flag | flag |

**Presets are a naming convention, not a resolver.** `preset` records intent; it does not populate rules. The reference implementation's `CompatibilityPolicy.rules_for()` ignores it — any surface you leave unset falls back to `keep`/`flag`/`drop`, so set the per-surface blocks explicitly to get the behavior above.

**With no policy at all, the fallback is deliberately non-destructive.** `classify_compatibility()` called without a policy never returns `drop`: no changes, or non-breaking changes only → `keep`; breaking changes confined to `output_contract` → `repair`; any other breaking change → `replay`. This is intentional — a caller who supplied no policy never has data discarded on their behalf. `drop` is reachable only through an explicit per-surface rule.

### Platform-only extensions

The fields below are implemented by the DecimalAI platform, not by the OSS schema/model. Do not put them in a policy you validate against `schemas/compatibility-policy.schema.json` — it will be rejected.

#### Source-Type Overrides (platform)

For distillation workflows, the teacher model is intentionally different from the student. The platform's `source_type_overrides` section lets policies skip the model compatibility check for non-production traces:

- `distillation`: Teacher-generated traces — skip model check
- `synthetic`: Synthetically generated — skip model check
- `manual`: Hand-written examples — skip model check

```json
{
  "source_type_overrides": {
    "distillation": { "model_runtime": { "on_minor": "keep", "on_moderate": "keep", "on_major": "keep" } },
    "synthetic":    { "model_runtime": { "on_minor": "keep", "on_moderate": "keep", "on_major": "keep" } },
    "manual":       { "model_runtime": { "on_minor": "keep", "on_moderate": "keep", "on_major": "keep" } }
  }
}
```

## Severity Thresholds

The severity classifiers use these thresholds:

| Surface | Minor | Moderate | Major |
|---------|-------|----------|-------|
| `prompt_stack` | ≤ 5% textual diff | ≤ 30% diff | > 30% diff |
| `model_runtime` | Config change only | Version bump within same family | Different provider **or** different model family |
| `tool_registry` | Tool added | Schema changed | Tool removed |
| `workflow` | Metadata changed | Edges changed | Nodes added/removed |
| `subagents` | Config changed | Agent added | Agent removed |
| `output_contract` | Format changed | Schema changed | Strict mode changed |
| `behavioral_policy` | Metadata only | — | Rules changed (breaking) |

## Policy Scoping

Policies can be scoped at two levels:

1. **Project-level**: Applies to all agents by default
2. **Per-agent override**: Agent-specific rules take priority

Resolution: agent override → project default → built-in `default` preset.

## Implementing this

A conforming implementation needs three things: somewhere to store a policy per
project and per agent, the resolution order above, and a way to preview a
policy's effect on a real manifest diff before applying it. Nothing here
requires a particular storage model or transport.
