# Evaluation Gates

> Status: Stable v1.0 · Added in v0.7.0

What evals the manifest was scored against, what thresholds applied, what scores it achieved. Provides the *evidence* that backs lifecycle transitions.

## Why this exists

Pre-v0.7 there was no machine-readable place to record "this manifest passed the regression suite with 0.97" or "this manifest cleared the safety eval at threshold 0.99." Promotions to production happened with the evidence sitting in Slack threads or CI run pages.

`evaluation.gates[]` puts that evidence on the manifest itself.

## Schema

```json
{
  "evaluation": {
    "gates": [
      {
        "name": "regression-suite",
        "dataset_ref": "dss_01HZK1A2B3C4D5E6F7G8H9J0K1",
        "threshold": 0.95,
        "actual_score": 0.972,
        "threshold_direction": "min",
        "passed": true,
        "ran_at": "2026-05-11T14:00:00Z",
        "evaluator_ref": "evr_regression_v3.2"
      },
      {
        "name": "safety-eval",
        "dataset_ref": "dss_01HZK1A2B3C4D5E6F7G8H9J0K2",
        "threshold": 0.99,
        "actual_score": 0.991,
        "passed": true,
        "ran_at": "2026-05-11T14:05:00Z"
      },
      {
        "name": "latency-p99",
        "threshold": 5000,
        "actual_score": 4180,
        "threshold_direction": "max",
        "passed": true,
        "ran_at": "2026-05-11T14:10:00Z",
        "notes": "ms; gpt-4o p99 under our latency budget."
      }
    ]
  }
}
```

## Fields per gate

| Field | Required | Description |
|---|---|---|
| `name` | Yes | A human-readable handle for the gate. Conventionally a slug. |
| `dataset_ref` | Optional | `dataset_snapshot_id` of the eval set. Lets you trace exactly which examples scored what. |
| `threshold` | Yes | The numeric threshold the score is compared against. |
| `actual_score` | Yes | The score the manifest achieved. |
| `threshold_direction` | Default `"min"` | `"min"` means actual must be ≥ threshold (higher is better — accuracy, F1, recall). `"max"` means actual must be ≤ threshold (lower is better — latency, cost, error rate). |
| `passed` | Yes | Whether the gate passed. The validator emits `eval_gate_inconsistent` (WARNING) when `passed` disagrees with `actual_score` vs `threshold` under the declared direction. |
| `ran_at` | Yes | When the eval was run (UTC, ISO 8601). |
| `evaluator_ref` | Optional | Reference to the evaluator code/config. Free-form string; conventions below. |
| `notes` | Optional | Free-text. |

## `evaluator_ref` conventions

The field is intentionally opaque to AgentVersion — it carries whatever pointer the consumer needs to find the evaluator that produced `actual_score`. Three conventions are common; implementations MAY use others.

### 1. Commit / version pointer

```
"evaluator_ref": "evr_regression_v3.2"
"evaluator_ref": "git+https://github.com/myorg/evals@a1b2c3d"
```

For evaluators that are versioned code in a repo. The value is implementation-defined; AgentVersion only stores it.

### 2. `skillevaluation://` URI scheme

Reference a [skillevaluation](https://github.com/decimal-labs/skillevaluation) test suite that produced the score:

```
"evaluator_ref": "skillevaluation://<suite-hash>@v<spec-version>"
```

Examples:
```
"evaluator_ref": "skillevaluation://abc123def456@v0.1.0"
"evaluator_ref": "skillevaluation://abc123def456@v1.0.0?case=tracks_with_id"
```

Where:
- `<suite-hash>` is the content hash of the `eval.yaml` suite (implementation-defined; SHA-256 hex of the canonicalized YAML is the default)
- `<spec-version>` is the `skillevaluation` spec version the suite is authored against
- An optional `?case=<name>` query parameter pins to a single case within the suite

This convention lets a consumer follow the reference back to:
- The test suite that produced the score
- The spec version it was authored against
- A specific case if the gate represents one case rather than the whole suite

### 3. External evaluator ID

```
"evaluator_ref": "deepeval://run_12345"
"evaluator_ref": "langsmith://project/my-evals"
```

For external eval systems. AgentVersion treats these as opaque strings.

## Validator semantics

- **`eval_gate_inconsistent` (WARNING)** — `passed` should match what the threshold direction implies. Example: threshold 0.95, actual 0.97, direction `min`, but `passed: false` → warning. (Useful for catching manually-edited manifest mistakes.)

## Hash participation

**Evaluation is NOT part of `contract`** — its contents do **not** affect `identity.overall_hash`. Evaluation evidence is about a manifest, not part of its identity. Re-running an eval against the same contract produces the same hash but updated evaluation data.

## Pairing with `lifecycle`

`lifecycle.history[].eval_ref` is the bridge from a lifecycle transition to the eval that justified it. Two valid conventions:

1. **By gate name** — `eval_ref: "regression-suite"` points at the gate of that name in `evaluation.gates`.
2. **By external reference** — `eval_ref: "evg_2026_05_11_regression"` points at an external record (a separate compatibility_decision, a CI run URL, an internal eval system ID).

The spec accepts both. Implementations decide their own convention.

## Recommended workflow

```
1. Engineer marks lifecycle.current_stage = "candidate" → triggers CI.
2. CI runs each eval, populates evaluation.gates[] with results.
3. Promotion logic checks: did every required gate pass?
4. If yes: append a transition to lifecycle.history with stage="staging"
   and eval_ref pointing at the latest gate run.
5. After soak in staging, repeat for "production".
```

The gates that gate promotion are agreed-upon out-of-band (typically in `CONTRIBUTING.md` for the agent's repo). The spec doesn't enforce *which* gates must pass — only that the gates that ran are recorded.
