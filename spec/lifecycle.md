# Lifecycle

> Status: Stable v1.0 · Added in v0.7.0

How a manifest moves from "someone is editing it" to "this is what production runs" and back to "this is archived." Captures the **transition history**, not just the current state.

## Why this exists

The pre-v0.7 `status` field is a single static enum: `draft | active | deprecated | archived`. It tells you what state the manifest is in *right now* but not how it got there. "Who promoted v3 to production, when, and based on what evidence?" had no answer.

The lifecycle block fixes that. Each transition is recorded with timestamp, actor, optional eval reference, optional approvers.

## Stages

| Stage | Meaning |
|---|---|
| `draft` | Work in progress. Not deployed anywhere. |
| `candidate` | Feature-complete; running through eval gates. |
| `staging` | Deployed to a non-production environment. |
| `production` | Serving real traffic. |
| `deprecated` | Still resolvable, but flagged as legacy. New work should not pin to this. |
| `archived` | Retained for audit/reference. Not callable. |

The stages are an *ordered enum* — `draft` is always "earlier" than `production`. Implementations may enforce forward-only transitions or allow rollbacks at their discretion (the spec is silent).

## Schema

```json
{
  "lifecycle": {
    "current_stage": "production",
    "history": [
      {
        "stage": "draft",
        "transitioned_at": "2026-05-01T10:00:00Z",
        "by": "user:stanley"
      },
      {
        "stage": "candidate",
        "transitioned_at": "2026-05-05T14:00:00Z",
        "by": "system:ci-pipeline",
        "eval_ref": "evg_regression_2026_05_05"
      },
      {
        "stage": "staging",
        "transitioned_at": "2026-05-08T09:00:00Z",
        "by": "system:deployer",
        "approved_by": ["user:eng-on-call"]
      },
      {
        "stage": "production",
        "transitioned_at": "2026-05-12T10:00:00Z",
        "by": "system:release-bot",
        "approved_by": ["user:stanley", "user:eng-on-call"],
        "notes": "Promoted after 4-day soak in staging."
      }
    ],
    "supersedes":     ["amf_01HZJ9ABCD…"],
    "superseded_by":  null,
    "sunset_at":      null
  }
}
```

## Fields

| Field | Required | Description |
|---|---|---|
| `current_stage` | Yes | The stage the manifest is in now. |
| `history` | Default `[]` | Ordered list of transitions. Oldest first. The validator requires the last entry's `stage` to equal `current_stage`. |
| `supersedes` | Default `[]` | List of `manifest_id`s this manifest replaces. Typically the previous production manifest. |
| `superseded_by` | Optional | The `manifest_id` that replaced this one (set when this manifest reaches `deprecated`). |
| `sunset_at` | Optional | Scheduled removal timestamp. Tools may warn callers when querying close to this date. |

### Transition entry

| Field | Required | Description |
|---|---|---|
| `stage` | Yes | The stage this transition moves to. |
| `transitioned_at` | Yes | When the transition happened (UTC, ISO 8601). |
| `by` | Yes | Actor identifier. Convention: `user:<id>`, `system:<id>` (e.g. `system:ci-pipeline`, `system:release-bot`). |
| `eval_ref` | Optional | Reference to evidence. Typically the name of an entry in `evaluation.gates`, a `compatibility_decision` ID, or an external URI. |
| `approved_by` | Default `[]` | List of approver identifiers. |
| `notes` | Optional | Free-text explanation. |

## Validator semantics

The reference validator enforces:

- **`lifecycle_history_unsorted` (ERROR)** — `history` must be sorted by `transitioned_at` ascending.
- **`lifecycle_stage_mismatch` (ERROR)** — `current_stage` must equal `history[-1].stage`.
- **`lifecycle_status_mismatch` (WARNING)** — if both `status` (simple) and `lifecycle.current_stage` (rich) are set, they must agree under this mapping:
  - `status: "draft"` ↔ `lifecycle.current_stage: "draft"`
  - `status: "active"` ↔ `"candidate"`, `"staging"`, or `"production"`
  - `status: "deprecated"` ↔ `"deprecated"`
  - `status: "archived"` ↔ `"archived"`

## Relation to `status`

Before v0.7, `status` was the only place to record a manifest's state. It's still supported for back-compat. New manifests should populate `lifecycle` and leave `status` empty (the validator will derive it).

The two will both remain through v1.0; v2.0 may drop `status` in favor of `lifecycle` only.

## Hash participation

**Lifecycle is NOT part of `contract`** — its contents do **not** affect `identity.overall_hash`. Two manifests with identical contracts but different lifecycle states are still the same logical version. Promoting a manifest from `candidate` to `production` is an operational fact, not a contract change.

## Pairs with `evaluation`

`lifecycle.history[].eval_ref` typically points at an entry in `evaluation.gates` (by `name`) or at an external reference. The pairing lets you say "this manifest reached `production` because the `regression-suite` gate passed with score 0.97 on 2026-05-12." See [`evaluation.md`](./evaluation.md).
