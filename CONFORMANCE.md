# Conformance

How an implementation proves it conforms to the AgentVersion.

## Why this exists

The spec is a multi-language target. The Python reference implementation lives in this repo, but an implementation in TypeScript, Rust, Go, or any other language is conforming as long as it produces the same outputs for the same inputs. This document defines "same outputs."

## What an implementation must do

A conforming implementation must support, at minimum:

1. **Manifest validation** — accept a manifest JSON, validate it against `schemas/agent-manifest.schema.json`, and enforce the semantic rules in `spec/manifest.md` § "Required fields" and § "Semantic Validation Rules" (`reference.md` §13).
2. **Canonical hashing** — given a manifest, produce the same `identity.overall_hash` as the Python reference for any input. The algorithm is JCS-SHA256 (RFC 8785) applied to the `contract` block as documented in [`spec/hashing.md`](spec/hashing.md). Quantization of `generation_config` floats is part of the spec.
3. **Diff** — given two manifests, produce a `manifest_diff` that matches the expected output of the conformance suite (described below).
4. **Compatibility classification** — given a `manifest_diff`, produce a `compatibility_report` whose `recommended_decision` matches the reference implementation's output for the same input.

Implementations may add additional capabilities (e.g. signing, registry resolution), but those are extensions and do not affect conformance.

## The conformance suite

Located under [`compatibility-tests/`](./compatibility-tests/). Each subdirectory is a scenario:

```
compatibility-tests/
  <scenario-name>/
    before.json          # input manifest A
    after.json           # input manifest B
    expected-diff.json   # ManifestDiff produced by a conforming implementation
```

Every subdirectory of `compatibility-tests/` is a scenario and all of them are normative — run the directory, not a fixed list.

The Python reference verifies conformance via `tests/test_conformance.py`. To verify an implementation in another language:

1. For each scenario, load `before.json` and `after.json`.
2. Run your implementation's diff function.
3. Compare your output against `expected-diff.json`.
4. The comparison must be tolerant to list ordering inside `changed_surfaces` (so use a set keyed on `(surface, change_type, severity)`), but the counts in `summary` and the set of surfaces and their `change_type`/`severity` must match exactly.

## Adding scenarios

When the spec gains new behavior, add a new scenario directory with a `before.json`, `after.json`, and `expected-diff.json` produced by the reference implementation. Open a PR that includes both the new scenario and any code changes required to pass it.

When existing semantics change, update the expected diffs in the same PR that changes the implementation. Both the implementation change and the fixture change must be reviewed together.

## What "matches" means

The reference comparison (see `tests/test_conformance.py`):

- `kind == "manifest_diff"`
- `old_manifest_id` and `new_manifest_id` match
- The set of `(surface, change_type, severity)` tuples in `changed_surfaces` is identical
- `summary.breaking_surfaces` and `summary.non_breaking_surfaces` counts match exactly

Things explicitly **not** part of conformance (intentionally tolerant):

- Order of items within `changed_surfaces` or `details` arrays
- Exact wording of human-readable strings in `details` (these are advisory, not contractual)
- `max_severity` field — derived; an implementation may omit or include it freely
