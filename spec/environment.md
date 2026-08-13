# Environment Surface

> Status: Stable v1.0 · Added in v0.6.0

The environment surface captures runtime + infrastructure facts that affect agent execution but aren't part of the agent's *logical* contract (prompts, tools, models, workflow).

## Why this exists

Pre-v0.6, the manifest had no way to record what environment an agent was deployed into. The `environment_unreplayable` reason code existed but had nothing concrete to compare against — implementations had to invent their own out-of-band convention.

The environment surface gives that out-of-band convention a name and a shape. Now an episode recorded under deployment-A image-X talking to API-v2.3.1 can be diffed against a current deployment-B image-Y talking to API-v2.4.0, and the rescue classifier can emit specific reasons (`region_changed`, `infra_image_changed`, `external_service_pin_changed`) instead of a generic `environment_unreplayable`.

## Schema

```json
{
  "contract": {
    "environment": {
      "deployment_id": "prod-east-1",
      "region": "us-east-1",
      "infra_image_hash": "sha256:5c8f9d3b…",
      "runtime_versions": {
        "python": "3.12.5",
        "node": "20.10.0",
        "app-runtime": "1.8.2"
      },
      "secret_refs": [
        "prod/openai-api-key",
        "prod/internal-db-creds"
      ],
      "external_service_pins": {
        "openai": "https://api.openai.com/v1@2024-10-01",
        "stripe": "stripe-2024-09-30.acacia",
        "internal-pricing-svc": "v3.2.1"
      },
      "feature_flags": {
        "new_router": true,
        "tool_v2_cutover_pct": 25
      },
      "resource_limits": {
        "memory_mb": 2048,
        "cpu_cores": 1.0,
        "timeout_seconds": 120,
        "max_concurrent_calls": 8
      }
    }
  }
}
```

All fields are **optional**. Manifests that don't need environment tracking can omit the block entirely and continue to validate.

## Fields

| Field | Type | Description |
|---|---|---|
| `deployment_id` | string | Identifier of the deployment instance. Often a slug like `prod-east-1` or `staging`. |
| `region` | string | Geographic region (e.g. `us-east-1`, `eu-west-2`). Affects data residency, network latency, and sometimes feature availability. |
| `infra_image_hash` | string | Hash of the container/VM image the agent runs in. Pins the entire OS + runtime layer. |
| `runtime_versions` | object | Map of `runtime → version`. Lists every runtime that affects execution: `python`, `node`, `app-runtime`, `sandbox-image`, etc. |
| `secret_refs` | array of strings | Names of secrets the agent consumes. **Never values.** Used to detect "this secret was rotated" vs "the agent now uses a different secret." |
| `external_service_pins` | object | Map of `service → pinned identifier`. The identifier is opaque to the spec: it can be a URL, API version string, semver, content hash — whatever lets you say "we were talking to *this* specific instance of the service." |
| `feature_flags` | object | Free-form map of flag → value. Used to capture A/B experiment state or rollout percentages that affect agent behavior. |
| `resource_limits` | object | Memory / CPU / timeout / concurrency bounds. Affects replayability (a 5-second timeout can't replay a trace that took 30 seconds) but not correctness. |

## Diff severity

Field-level severity rules (see `agentversion.diff.environment_severity`):

| Field changed | Severity | Why |
|---|---|---|
| `deployment_id` | minor | Rename / blue-green swap; same logical environment. |
| `secret_refs` | minor | Secret rotation; the agent still uses the same logical credentials. |
| `feature_flags` | minor | Behavior tuning; doesn't invalidate past traces. |
| `resource_limits` | minor | Performance envelope, not correctness. |
| `region` | moderate | Data residency, network latency. Replay may give different responses if downstream services are region-pinned. |
| `infra_image_hash` | moderate | Different OS / language runtime / tool implementations. |
| `runtime_versions` | moderate | E.g. `python 3.10 → 3.12` can shift JSON-serialization, hash ordering, library behavior. |
| `external_service_pins` | moderate | A downstream API version bump may change tool outputs. |

Environment changes never escalate to `major` automatically — major is reserved for changes that *invalidate past traces*. Environment changes affect *replayability*, which is the concern of `replay_plan.replayability` (`fully_replayable` / `partially_replayable` / `not_replayable`), not validity of recorded data.

## Reason codes

When a compatibility decision involves the environment surface, the classifier may emit any of:

- `region_changed`
- `infra_image_changed`
- `external_service_pin_changed`
- `runtime_version_changed`
- `environment_unreplayable` — catch-all when the environment recorded with an episode no longer exists (e.g., the deployment was decommissioned)

## Compatibility policy

The environment surface can be configured in `CompatibilityPolicy` like any other surface:

```json
{
  "kind": "compatibility_policy",
  "name": "strict-prod",
  "environment": {
    "on_minor": "keep",
    "on_moderate": "flag",
    "on_major": "drop"
  }
}
```

A common setup: `flag` on moderate so a human reviews the impact of an infra image bump before promoting the new manifest.

## Hash participation

The environment surface is part of `contract`, so its content **does** participate in `identity.overall_hash`. Two manifests with identical agents but different deployments (e.g., `prod-east-1` vs `prod-west-2`) will hash differently. This is intentional — operational identity matters for replay.

If you need "same agent across regions" semantics (one logical version, multiple physical deployments), set only `deployment_id` (minor severity) and leave `region` / `infra_image_hash` empty; or model the cross-region case via per-deployment child manifests.

## Security

- `secret_refs` holds **names**, not **values**. Implementations that violate this requirement leak credentials into version-controlled artifacts.
- `external_service_pins` values are public-ish identifiers (URLs, versions). Don't put bearer tokens there.
- The environment block is inside `contract`, so it is covered by `identity.overall_hash` — sign that hash via `identity.attestations[]` to detect tampering by infrastructure that shouldn't be modifying contract state. See [attestation.md](./attestation.md) (§3d).
