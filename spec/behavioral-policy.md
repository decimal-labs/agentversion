# `behavioral_policy` surface

A contract surface that binds an agent to a **versioned policy document** — the rules it must hold to.
The surface is document-agnostic: the policy can be a refund/escalation policy (*"deny refunds and offer
alternatives; only after the customer has objected ≥3 times, escalate to a human; never concede a refund
yourself, and never admit liability"*), a safety guardrail set, an escalation SOP, or any other bound
rule artifact.

## Why it is a first-class surface

A behavioral policy usually lives *inside the system prompt*. Before this surface existed, flipping the
policy (tightening a threshold, or dropping a forbidden rule) showed up only as a `prompt_stack`
**hash change**, which the diff classifies **`non_breaking`** → recommended decision **`keep`**. But a
policy flip **invalidates** any eval set and any past traces that were graded under the old policy.
Hoisting the policy to its own surface makes that flip **`breaking`** → `replay`/`drop`, instead of
silently retaining now-wrong data.

The `policy_hash` is the canonical identity — a hash of *whatever policy artifact you bind*. The
structured rule fields below are optional and carried only for human-readable diffs; the surface does not
interpret them.

## Shape

```json
"behavioral_policy": {
  "policy_id": "refund-escalation",
  "policy_hash": "sha256:…",          // hash of the bound policy artifact (the identity)
  "objection_threshold": 3,           // optional structured rule fields — illustrative,
  "concede_events": ["offered_refund", "escalated"],   // carried for readable diffs only
  "always_forbidden": ["admits_liability"]
}
```

`policy_id` and `policy_hash` are the only load-bearing keys. The structured rule fields
(`objection_threshold`, `concede_events`, `always_forbidden`) are **optional**, illustrative, and kept
for backward compatibility with policies already bound this way — a policy artifact needn't populate any
of them. The model is `extra="allow"`, so a richer or differently-shaped policy spec round-trips without
forking it.

## Diff semantics

| Transition | Classification | Rationale |
|---|---|---|
| rule change (`policy_hash` differs, or any rule field differs) | **breaking** (`major`) | any eval set + past graded traces are now wrong |
| `policy_hash` unchanged, only metadata (`policy_id`) differs | `non_breaking` (`minor`) | same policy, no rule changed |
| introduced (absent → present) | `non_breaking` | the old eval set tested no policy; additive |
| removed (present → absent) | **breaking** (`major`) | past data graded under the policy is now ungoverned |

Reason code: `behavioral_policy_changed`. Configurable per-surface via `CompatibilityPolicy.behavioral_policy`
(defaults: `on_major` → `drop`).

## Hash-safety

`behavioral_policy` is **optional and omitted by default**. The `overall_hash` is computed only over the
surfaces actually present in a contract, so adding this surface to the spec does **not** change the hash
of any existing (policy-less) manifest. The frozen hash-vectors are unchanged.
