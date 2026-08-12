# AgentVersion — Reference

**Where the protocol lives.** Each spec object has its own file; this page is the index.

> The Pydantic models and JSON Schemas under `agentversion/` and `schemas/` are the source of truth.

## Spec objects

- §1 **Agent Manifest Spec (`agentversion.json`)** → [manifest.md](./manifest.md)
- §2 **Agent Dataset Spec** → [dataset.md](./dataset.md)
- §3 **Compatibility Decision Spec** → [compatibility-decision.md](./compatibility-decision.md)
- §4 **Replay Job Spec** → [replay.md](./replay.md)
- §5 **Diff Spec** → [diff.md](./diff.md)
- §10 **Canonical Hashing Algorithm** → [hashing.md](./hashing.md)
- §11 **Versioning Policy** → [versioning-policy.md](./versioning-policy.md)
- §12 **Compatibility Batch Spec** → [compatibility-batch.md](./compatibility-batch.md)

## Capability items (§3a–§3n)

`§3a`–`§3n` appear throughout the spec and the code as shorthand for the
individual capability items that were added to the manifest surface. They are
*not* subsections of §3 (the Compatibility Decision Spec) — the letter suffix is
a separate index. Where an item shipped its own release, the CHANGELOG entry of
the same name carries the rationale.

| Item | Capability |
| --- | --- |
| §3a | Environment fingerprint surface |
| §3b | Canonical IDs (and generalized ID enforcement) |
| §3c | Manifest references |
| §3d | Attestation |
| §3e | Lifecycle |
| §3f | Replay determinism hints |
| §3g | Tool schema embedding |
| §3h | Model cost & limits envelope |
| §3i | Tool `semantic_version` |
| §3j | Manifest tombstone |
| §3k | Evaluation gates |
| §3l | No standalone surface; nothing in the spec carries this letter |
| §3m | Richer `ComparisonSummary` |
| §3n | Data classification |

## Cross-cutting concerns

- §10 **Canonical Hashing Algorithm** → [hashing.md](./hashing.md)
- §11 **Versioning Policy** → [versioning-policy.md](./versioning-policy.md)
- **Compatibility Policy** (user-configurable rules) → [compatibility-policy.md](./compatibility-policy.md)
- **OpenTelemetry Mapping** → [otel-mapping.md](./otel-mapping.md)

---

## Appendix: original reference content

The sections below were kept inline because they describe the protocol as a whole, not a single spec object. They will move to dedicated files in a future restructure.

# 6. Repo File Layout

> Representative, not exhaustive. The `/spec`, `/schemas`, and `/agentversion`
> directories carry more files than shown here; the canonical contents are
> whatever is checked into the repo. The skeleton below orients new readers.

```text
agentversion/
  README.md
  LICENSE                              # Apache 2.0
  CHANGELOG.md
  CONFORMANCE.md
  CONTRIBUTING.md
  RELEASING.md
  pyproject.toml                       # Package: agentversion
  scripts/                             # release / maintenance scripts
  tests/                               # test suite

  /spec                                # one file per spec object + cross-cutting concern
    reference.md                       # this index
    manifest.md
    dataset.md
    replay.md
    replay-determinism.md
    compatibility-decision.md
    compatibility-batch.md
    compatibility-policy.md
    diff.md
    hashing.md
    versioning-policy.md
    lifecycle.md
    evaluation.md
    attestation.md
    behavioral-policy.md
    environment.md
    data-classification.md
    ids.md
    refs.md
    a2a-mapping.md
    otel-mapping.md

  /schemas
    agent-manifest.schema.json
    task.schema.json
    episode.schema.json
    step.schema.json
    dataset-snapshot.schema.json
    compatibility-decision.schema.json
    compatibility-batch.schema.json
    compatibility-policy.schema.json
    compatibility-report.schema.json
    replay-job.schema.json
    replay-result.schema.json
    manifest-diff.schema.json

  /agentversion                           # Python reference implementation
    __init__.py
    manifest.py
    hasher.py
    diff.py
    compatibility.py
    decision.py
    replay.py
    dataset.py
    validator.py
    cli.py
    ids.py
    refs.py
    a2a.py
    constants.py
    _shared.py
    py.typed

  /examples
    manifest/
    scenarios/
    integrations/
      langgraph_example.py
      otel_mapping.md

  /adrs
    0001-version-spec-core.md
```

---


# 7. Pydantic Models

The authoritative models live under `agentversion/` (`manifest.py`, `dataset.py`, `decision.py`, `replay.py`) and are the source of truth (see the note at the top of this page). This section previously inlined copies of them, but those drifted from the code (missing `lifecycle`, `evaluation`, `model_runtime.envelope`, tool `semantic_version`, and the identity attestation/yank fields). Consult the modules directly for the current field set.

---


# 8. CLI Surface

Core commands:

```bash
agentversion --version
agentversion validate agent-manifest.json
agentversion diff old-manifest.json new-manifest.json
agentversion init
agentversion hash agent-manifest.json
agentversion upgrade old.json --to 1.1.0
agentversion replay validate replay-job.json
agentversion decision validate compatibility-decision.json
agentversion decision generate old-manifest.json new-manifest.json
agentversion dataset validate dataset-snapshot.json
```

---


# 9. JSON Schema Files

The authoritative JSON Schemas live under `schemas/`:

- **Manifest:** `agent-manifest.schema.json`
- **Dataset objects:** `task.schema.json`, `episode.schema.json`, `step.schema.json`, `dataset-snapshot.schema.json`
- **Compatibility:** `compatibility-decision.schema.json`, `compatibility-batch.schema.json`, `compatibility-report.schema.json`, `compatibility-policy.schema.json`
- **Replay & diff:** `replay-job.schema.json`, `replay-result.schema.json`, `manifest-diff.schema.json`

This section previously inlined copies of three of these schemas, but they drifted from the published files (the manifest schema was even named `agentversion.schema.json` here). Consult `schemas/` directly.

---


# 13. Semantic Validation Rules (Beyond JSON Schema)

JSON Schema handles structure. `agentversion validate` (the reference manifest validator,
`agentversion/validator.py`) layers the semantic rules below on top. Each
bullet leads with the issue `code` it emits and its severity, so the list can be
checked against the implementation.

**Identity & hashing:**

* `hash_mismatch` (warning) — `identity.overall_hash` must be reproducible from the normalized manifest (see §10)
* `unsupported_hash_algorithm` (warning) — `identity.hash_algorithm` should be `"jcs-sha256"`

**Lineage & references:**

* `self_referencing_parent` (error) — `parent_manifest_id` must not equal `manifest_id`
* `malformed_manifest_ref` (error) — each subagent `manifest_ref` must parse as a typed URI (`agentversion:manifest:<id>`, `agentversion:hash:<algo>:<hex>`, `https://…`, or `file://…`)
* ID-format checks (error/warning) — object IDs must match the canonical `<prefix>_<ULID>` form (delegated to `ids.check_object_ids`)

**Lifecycle (§3e):**

* `lifecycle_history_unsorted` (error) — `lifecycle.history` must be sorted by `transitioned_at` (oldest first)
* `lifecycle_stage_mismatch` (error) — `lifecycle.current_stage` must equal the last history entry's stage
* `lifecycle_status_mismatch` (warning) — the simple `status` field must agree with `lifecycle.current_stage`

**Tools (§3g, §3i):**

* `duplicate_tool_hash` (warning) — each tool `hash` should be unique within a registry
* `schema_hash_mismatch` (error) — a tool's `input_schema_inline` / `output_schema_inline` must hash to its declared `*_schema_hash`
* `malformed_semver` (warning) — a tool's `semantic_version`, if present, must be valid semver

**Evaluation (§3k):**

* `eval_gate_inconsistent` (warning) — each gate's `passed` must agree with `actual_score` vs `threshold` / `threshold_direction`

**Not yet enforced (planned, cross-object):**

These pertain to compatibility-decision, replay-job, and compatibility-batch
objects rather than manifests. `agentversion decision validate`, `agentversion replay validate`,
and `agentversion dataset validate` currently perform structural (Pydantic / JSON Schema)
validation only — they do not yet check:

* if `decision = replay`, then `replay_plan` should usually be present
* if `decision = repair`, then `repair_plan` should usually be present
* if replay `mode = analysis_only`, requested outputs should not require full replay artifacts
* compatibility-batch `summary` counts should sum to `total_episodes`

---


# 14. Scope

**In scope:**

* identity
* diffability
* lineage
* replayability
* compatibility decisions

**Out of scope:**

* full raw prompt text embedded by default
* giant tool schemas inline by default
* model-provider-specific low-level details
* full eval rubric schema
* annotation workflow schema
* anything too UI-specific
* anything tightly coupled to the hosted platform

---


# 15. Core Design Rule

The standard must cleanly answer four questions:

1. **What runtime contract produced this trace?**
2. **How is this runtime different from the new one?**
3. **Can this old example still be used?**
4. **If not, should it be repaired, replayed, or dropped?**

---


# 16. Reference Implementation

The spec ships with all of the following:

* the markdown spec documents
* the JSON Schemas
* a Python validator CLI
* 3–5 realistic example manifests
* 3 realistic drift scenarios
* one LangGraph integration example
* one OpenTelemetry mapping example

