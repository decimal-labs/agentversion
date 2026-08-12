# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Package version ≠ spec version.** This file tracks the **package** version. The on-the-wire `spec_version` is independent and frozen at `1.0.0`; a pre-1.0 package can implement a stable 1.0 spec, which is exactly the situation today.

## [0.2.2] - 2026-07-15

### Changed
- **`behavioral_policy` re-scoped as a generic versioned policy-document surface** (docs only).
  The surface previously described itself as bound to skillevaluation's conversation-mode
  `policy_check` state machine; that eval mode was removed (skillevaluation ADR-0007), so the
  docstrings + `spec/behavioral-policy.md` now define it document-agnostically: `policy_hash` is a
  hash of *any* bound policy artifact (refund rules, a safety guardrail set, an escalation SOP…),
  a rule change diffs **breaking**, an unchanged `policy_hash` is non-breaking. **No code or schema
  change**: the `BehavioralPolicy` model still carries `objection_threshold`/`concede_events`/
  `always_forbidden` (now documented as optional, illustrative, back-compat rule fields), the
  `_BEHAVIORAL_POLICY_RULE_FIELDS` diff logic is byte-identical, and every frozen hash-vector +
  the 406-test suite are unchanged. `spec_version` unchanged (1.0.0).

## [0.2.1] - 2026-06-24

### Fixed
- **`contract_from_components` now emits the `behavioral_policy` and
  `environment` surfaces.** 0.2.0 added the models, surface keys, and diff
  classifiers, but the shared flat-components → contract assembler silently
  dropped both — so a producer (the DecimalAI SDK / the platform) could never
  actually populate them from components. They are now assembled verbatim from
  each component's `schema_json`. Additive-only: a manifest that doesn't declare
  them is unchanged (same `overall_hash`).
- **`tool_calling_mode` and `runtime_version` are now lifted to `model_runtime`
  top level** (not buried in `model_config_hash`), so a `tool_calling_mode`
  change is classified **breaking** by the diff as intended, and
  `runtime_version` participates in `model_runtime` severity.

The DecimalAI SDK exporter (`ManifestSnapshot.to_agentversion`) was edited
byte-identically and is pinned to this assembly by its conformance test.
`SPEC_VERSION` is unchanged (1.0.0) — these surfaces were already in the spec.

## [0.2.0] - 2026-06-24

### Added
- **`behavioral_policy` contract surface** — a first-class surface for a multi-turn agent's behavioral
  policy (the rules it holds across turns: a refund/escalation policy, etc.), bound to skillevaluation's
  conversation-mode `policy_check`. A change to the RULES diffs as **breaking** → `replay`/`drop`, where
  previously a policy flip lived only in the prompt-stack hash and read `non_breaking` → `keep`, silently
  retaining a now-invalid conversation eval set. Optional + omitted by default, so existing manifests'
  `overall_hash` is **unchanged**. Reason code `behavioral_policy_changed`; spec `spec/behavioral-policy.md`.
- **A2A Agent Card mapping** (`a2a.manifest_to_agent_card`, exported): project a manifest onto an
  [A2A (Agent2Agent)](https://a2a-protocol.org/) Agent Card, stamping the manifest's identity
  (`manifest_id` + `overall_hash`) under an `x-agentversion` provenance block so a card consumer can pin
  the exact versioned contract it describes. Positions AgentVersion as the version/diff/provenance layer
  **on top of** the A2A interop standard rather than a competing descriptor. Spec: `spec/a2a-mapping.md`.
- **Extension hatch** (`AgentContract` is now `extra="allow"`): a custom / emerging contract surface
  (RAG corpus, MCP server registry, memory policy, vendor extension) is hashed by the hasher and diffed
  by the engine, and now also **survives `model_validate`** — previously it was silently dropped, so a
  validate→re-serialize→re-hash round-trip changed `overall_hash` (a moat-breaking non-determinism). The
  surface set can grow without forking the model. ASCII/known-surface hashes are unchanged.
- **`COMPONENT_TYPE_TO_SURFACE` + `surface_key_for_component()`** — the canonical routing from a
  producer's flat `component_type` to the contract surface key it lands in (incl. the singular→plural
  `guardrail`→`guardrails` rename). Exported so a producer (the SDK exporter) and a consumer (a diff
  translator) share one source of truth instead of hand-copying the map — closing a cross-stack drift
  class where the rename had to be applied independently in every translator copy.
- **`contract.contract_from_components()`** — the single source of truth for assembling a contract block
  (every surface, in canonical shape) from a producer's flat component list. Both the DecimalAI SDK
  exporter and the platform's hash path route through it, so they compute the *same* `jcs-sha256`
  identity hash for the same agent — the platform can now make the canonical hash authoritative and a
  customer reproduces the stored hash with the OSS CLI. Replaces two hand-written
  translators that shared no code or test.

### Fixed (hash-determinism + trust)
- **Canonical-hash domain** (`hasher.py`): NFC-normalize every string (keys + values) and reject
  non-finite floats (`NaN`/`±Infinity`) **before** JCS canonicalization. JCS canonicalizes bytes but
  does not Unicode-normalize, so a composed `"café"` and a decomposed `"café"` previously produced a
  different `overall_hash` for the same agent (a cross-language reproduction break in the moat); and a
  `NaN` raised an opaque `jcs` error instead of a clear domain error. NFC of ASCII is a no-op, so
  **existing manifest hashes are unchanged** (frozen vectors still pass). Documented in `spec/hashing.md`.
- **Attestation integrity** (`validator.py`): an attestation's `signed_payload_hash` must equal the
  manifest's declared `overall_hash` (error on mismatch) — the no-crypto linkage that proves the
  attestation covers *this* manifest. Previously the envelope was parsed but never checked, so a
  copy-pasted/tampered attestation rode along inertly. Cryptographic signature verification remains
  explicitly delegated to a verifier (out of scope for the validator).

### Fixed (correctness audit)
- **Schema ↔ code drift on `behavioral_policy`** — the bundled `manifest-diff.schema.json` surface enum
  was missing `behavioral_policy`, and neither `decision.REASON_CODES` nor `compatibility-decision.schema.json`
  listed `behavioral_policy_changed`, even though the diff/compat code **emits** both. A diff or decision
  touching the policy surface therefore failed its own bundled schema. Both schemas + `REASON_CODES` now
  include them. (`spec_version` stays `1.0.0` — these are compatible additions to an already-declared surface.)
- **`model_runtime` reason code** — a model swap mapped to `prompt_policy_changed` (there was no model
  reason code at all). Added `model_runtime_changed` to `REASON_CODES` + the decision schema, and remapped
  the `model_runtime` surface to it.
- **`output_contract` severity tiers corrected to match the normative spec** (`spec/compatibility-policy.md`):
  was format→moderate, schema→major, strict→(no bump); now **format→minor, schema→moderate, strict→major**
  (a strict-mode flip newly *rejects* previously-valid outputs, so it is the most consumer-breaking). A
  `strict` change is now also `breaking`. The `output-schema-change` conformance fixture's expected severity
  was corrected `major`→`moderate` accordingly: the fixture encoded the buggy output, so this is a defect
  correction, not a change to a stable conformance scenario.
- **Asymmetric add/remove diffs** — a surface that *appeared* or *vanished* bypassed its dedicated
  classifier and got a flat generic verdict (add→moderate/non_breaking, remove→breaking/major), so
  `diff(A,B)` was not the inverse of `diff(B,A)` (e.g. an added `output_contract{strict:true}` read as a
  bland "moderate" instead of major). Add/remove now route through the dedicated classifier against an
  empty sentinel, so a surface appearing/vanishing is severitied by the same logic as an in-place change.
  Introducing a `behavioral_policy` stays additive (non_breaking); removing one stays breaking.
- **Model-family extraction missed compact date stamps** — `_extract_model_family` stripped dashed dates
  (`gpt-4o-2024-08-06`) but not compact 8-digit Anthropic dates (`claude-3-5-sonnet-20241022`), so a routine
  model date-rev read as a *different family* → spurious `major`/`replay`. Now strips `\d{8}` (and applies
  iteratively); genuine family changes (`gpt-4` vs `gpt-4o`) are preserved.
- **Validator hardening** — `CompatibilityDecision.reason_codes` are now validated against `REASON_CODES`
  (the schema enforced this on the wire; the model didn't); `validate_manifest(..., check_schema=True)` is a
  new opt-in pass that validates against `agent-manifest.schema.json` (catches unknown top-level keys the
  Pydantic models silently drop); a manifest whose contract can't be canonically hashed (e.g. a non-finite
  float) is now an **error** (`hash_uncomputable`), not a soft warning that still validated.
- **Lower-severity:** unnamed subagents are keyed by content hash rather than list position (removing one of
  several no longer reads as a positional rename); `prompt_severity` boundary at exactly 5.0% is now `minor`
  to match the spec's `≤5%` (was `moderate`).

### Documentation & packaging
- **The wheel now bundles `spec/`, `examples/`, and `compatibility-tests/`** (previously only `schemas/`), so a
  `pip install`ed user actually has the files the README points at. Dropped the false `pytest --pyargs agentversion`
  claim (tests aren't bundled) in favor of a clone-and-test snippet.
- **New `examples/integrations/decimalai_bridge.py`** and a README **"From the DecimalAI SDK"** section showing
  the `decimalai.export_manifest(snap)` → `agentversion diff` round-trip — the seam that makes agentversion the
  open core of the paid platform was previously undocumented. The `decimalai-python` README now references it too.
- **Fixed the README** `evaluation.gates[]` example (was missing the required `ran_at` → failed validation on
  copy-paste) and regenerated the "See it in action" diff table to match current output (the `environment` row now
  shows real field-level changes instead of a bland "environment added").
- **`langgraph_example.py`** rewritten to compute real content hashes (was emitting placeholder `sha256:extract_from_*`
  strings) and to actually validate; **`examples/scenarios/walkthrough.py`** is a new runnable, test-covered version
  of the tool-rename drift scenario. A new smoke test runs every example so they can't bit-rot.
- Stale-terminology fixes: `compatibility-batch.md` example id `rcb_` → `cbt_`.

## [0.1.0] - 2026-05-29

**First published release** — the first `agentversion` release on PyPI.

The package ships pre-1.0 on purpose. The spec it implements is stable (`spec_version 1.0.0`, with a frozen wire format and conformance suite), but the Python package API hasn't earned its own 1.0 promise yet — so it enters at `0.1.0` (`Development Status :: 4 - Beta`). Feature-wise it's complete against the original capability roadmap; that work landed across the internal milestones listed further below, none of which were ever published.

### Changed — Project renamed to **AgentVersion**

The project was renamed from "Agent Version Spec (AVS)" to **AgentVersion** before its first public release. The on-the-wire `spec_version` is unchanged (still `1.0.0`); only names and identifiers changed. Because nothing was published prior to this, there is no migration path — the rename is a pre-release change.

- **PyPI distribution**: `agent-version-spec` → `agentversion`.
- **Python import / package**: `agent_version_spec` → `agentversion`.
- **CLI command**: `avs` → `agentversion`.
- **Manifest-ref URI scheme**: `avs:manifest:<id>` / `avs:hash:<algo>:<hex>` → `agentversion:manifest:<id>` / `agentversion:hash:<algo>:<hex>`. Manifests that carry subagent `manifest_ref`s must update those values and recompute `identity.overall_hash` (refs are inside the hashed `subagents` surface). The example `examples/manifest/finance-agent-v2.json` was updated accordingly.
- **OpenTelemetry attribute key**: `agent_version_spec.manifest_hash` → `agentversion.manifest_hash`.
- **GitHub repository**: `decimal-labs/agent-version-spec` → `decimal-labs/agentversion`.

Unchanged: object ID prefixes (`amf`, `tsk`, `ep`, `dss`, `cdc`, `rpj`, `rpr`, `mdf`), the `spec_version` value (`1.0.0`), the `jcs-sha256` hash algorithm, and the schema file names (which are object-named, not project-named).

---

## Pre-release development (internal milestones — never published)

The entries below were development milestones tracked in-repo on the way to feature-completeness. None were published to PyPI or any other index, so there is no migration path between them — they're kept as a record of how the spec took shape. Their version numbers are the old internal numbering and overlap the published `0.1.0` above only by coincidence.

### 1.0.0 - 2026-05-12 (internal milestone)

**Feature-complete milestone** (never published). The capability roadmap reached feature-completeness at this internal version; the stability promise it anticipated now lives on the spec, which is frozen at `1.0.0`.

### What v1.0 looks like

- **Canonical IDs only.** Every ID matches `^[a-z][a-z0-9]*_[0-9A-HJKMNP-TV-Z]{26}$` (kind-prefixed ULID). The JSON Schema, Pydantic models, and semantic validator all enforce this. `malformed_id` and `wrong_id_prefix` are errors; there is no permissive mode.
- **Typed manifest references only.** `subagents[].manifest_ref` accepts `avs:manifest:<canonical-id>`, `avs:hash:<algo>:<hex>`, `https://...`, or `file:///...`. Bare IDs are rejected. `malformed_manifest_ref` is an error.
- **`Development Status` classifier**: `5 - Production/Stable`.
- **Conformance suite frozen.** `compatibility-tests/` scenarios in v1.0.0 stay stable through v1.x. New scenarios may be added in minors; existing ones don't change.
- **Semver locked.** `1.x.0` minors are always backward-compatible (additive only). Anything that removes/renames/tightens requires a major bump.

### Migration

There is no migration path from pre-v1.0 — nothing pre-v1.0 was released. Build new manifests at canonical form.

### What's next

- v1.x minors: federated registry resolution, well-known `extensions` namespace registry, streaming manifest support.
- v2.0 (no timeline): drop legacy `status` field in favor of `lifecycle.current_stage` only.

### 0.9.0 - 2026-05-12

Trust + observability + governance batch. The last three §3 items.

### Added — Attestation (§3d)
- **`Attestation` model** with `signer`, `algorithm`, `signature`, `signed_payload_hash`, `signed_at`, optional `key_id` + `expires_at`.
- **`IdentityBlock.attestations: List[Attestation]`** — multiple attestations supported (typical: CI provenance + release-manager approval + security-scan).
- **Hash isolation**: attestations live on `identity` (not `contract`), so adding or rotating signatures does NOT change `overall_hash`. A manifest's identity is its contract; signatures are evidence about it.
- **Verification is out of spec**: format-only. Implementations bring their own crypto (Sigstore, cosign, GPG, internal PKI). The validator only enforces well-formedness; it does not check signatures.
- Spec doc [`spec/attestation.md`](./spec/attestation.md).

### Added — Richer `ComparisonSummary` (§3m)
- **New fields on `ReplayResult.comparison_summary`**: `final_output_diff_pct` (0-100), `tool_path_diff: ToolPathDiff` (`steps_added`, `steps_removed`, `first_divergence_step_index`), `step_count_delta`, `latency_delta_ms`, `cost_delta_usd`, `eval_score_delta`. All optional — back-compat preserved.
- **`ToolPathDiff` model** for structural diff of the tool-call sequence.
- **Use case**: sort divergent replays by severity. Pre-v0.9, you knew which replays diverged; now you know *how much* and *where* they first diverged.

### Added — Data Classification (§3n)
- **`DataClassification` model** for compliance labels: `pii_state` (`raw|redacted|synthetic|none`), `retention_days`, `residency[]`, `redaction_policy_ref`, `consent_basis` (GDPR Article 6 enum).
- **`DatasetSnapshot.data_classification`** — optional; defaults to `pii_state="none"` when present without overrides.
- **`SelectionPolicy.pii_states`** — filter so a snapshot can declare "only include episodes whose data is redacted or synthetic".
- Spec doc [`spec/data-classification.md`](./spec/data-classification.md).

### Tests
- 17 new tests in `tests/test_trust_observability.py`.
- avs total: **295 passing** (was 278, net +17).

### Phase 3 complete
All 14 capability items (§3a–§3n) are now shipped, except §3l, which ships no standalone surface of its own. The spec is feature-complete for that roadmap. Next milestone: **v1.0** — tighten enforcement (drop permissive ID pattern, drop bare-ID manifest_refs), publish to PyPI.

### 0.8.0 - 2026-05-12

Reproducible-replay batch. Four audit items in one bump because they collectively make most agents bit-reproducibly replayable — adding one without the others leaves replay still flaky.

### Added — Tool semantic_version (§3i)
- **`ToolDescriptor.semantic_version`** — SemVer string catching *behavioral* drift that schema hashes miss (e.g. "we swapped the upstream Census API from 2019 to 2024; same schema, different numbers").
- **`ToolDescriptor.implementation_ref`** — opaque pointer to the implementation (git commit, image hash, etc.).
- **Diff classifier extension**: when schemas are unchanged but a tool's `semantic_version` bumps, the diff now flags the bump kind — major → breaking moderate, minor → non-breaking minor, patch → non-breaking minor.
- **Validator code**: `malformed_semver` (WARNING).

### Added — Tool schema embedding (§3g)
- **`ToolDescriptor.input_schema_inline`** and **`output_schema_inline`** — optional inline JSON Schemas alongside the existing hashes.
- **Validator code**: `schema_hash_mismatch` (ERROR) when `JCS-SHA256(inline) != declared hash`.
- Enables fully-offline replay: archived agents don't need a live registry to verify tool I/O.

### Added — Model cost & limits envelope (§3h)
- **`ModelRuntime.envelope`** — new sub-object with `context_window_tokens`, `expected_latency_ms_p50` / `p99`, `cost.{input,output,cached_input}_per_1k_tokens_usd`, `rate_limit.{rpm,tpm}`.
- Anchors `ReplayConstraints.max_cost_usd` budgeting and lets the diff classifier flag price-tier swaps.
- Envelope is part of `contract.model_runtime` → participates in `overall_hash`. Provider price changes warrant a new manifest version.

### Added — Replay determinism hints (§3f)
- **`ReplayInput.determinism`** — new optional sub-object with `random_seed`, `clock_freeze_at`, `tool_response_pinning_ref` (the last a `ManifestRef`-style URI; `avs:hash:` is the typical scheme since you want tamper detection).
- Spec doc [`spec/replay-determinism.md`](./spec/replay-determinism.md) covers all four §3f/§3g items together and explains why they ship as a set.

### Examples
- `finance-agent-v2.json` gains a populated `envelope` on `model_runtime` and a `semantic_version` + `implementation_ref` on `get_market_cap`. `overall_hash` updated because both fields are in-contract.

### Tests
- 14 new tests in `tests/test_reproducible_replay.py`.
- avs total: **278 passing** (was 264, net +14).

### 0.7.0 - 2026-05-12

### Added — Lifecycle (§3e)
- **`Lifecycle` model** as an optional top-level field on `AgentManifest` (siblings: `lifecycle`, `evaluation` — both outside `contract`, so they do NOT participate in `identity.overall_hash`).
- Six stages: `draft → candidate → staging → production → deprecated → archived`.
- `LifecycleTransition` records each promotion: `stage`, `transitioned_at`, `by` (actor convention: `user:<id>`, `system:<id>`), optional `eval_ref`, `approved_by[]`, `notes`.
- `supersedes[]` and `superseded_by` for the version-chain bookkeeping. `sunset_at` for scheduled removal.
- Validator: `lifecycle_history_unsorted` (ERROR), `lifecycle_stage_mismatch` (ERROR), `lifecycle_status_mismatch` (WARNING — when the simple `status` field and `lifecycle.current_stage` disagree under the simple-to-rich mapping).
- Spec doc [`spec/lifecycle.md`](./spec/lifecycle.md).
- 13 new tests in `tests/test_lifecycle.py`.

### Added — Evaluation Gates (§3k)
- **`Evaluation` model** as an optional top-level field carrying `gates[]`. Like lifecycle, NOT in contract — re-running an eval against the same agent produces the same `overall_hash` but updated evaluation data.
- `EvalGate` records: `name`, optional `dataset_ref`, `threshold`, `actual_score`, `threshold_direction` (`"min"` higher-is-better / `"max"` lower-is-better), `passed`, `ran_at`, optional `evaluator_ref`, `notes`.
- Validator: `eval_gate_inconsistent` (WARNING) when `passed` disagrees with `actual_score` vs `threshold` under the declared direction.
- Spec doc [`spec/evaluation.md`](./spec/evaluation.md).
- 9 new tests in `tests/test_evaluation.py`.

### Added — Manifest Tombstone (§3j, folded in)
- `IdentityBlock.yanked_at` and `IdentityBlock.yanked_reason` — optional fields for marking a published manifest as no-longer-recommended without rewriting history (PyPI-yank semantics).
- Identity block is NOT part of contract, so yanking a manifest does NOT change its `overall_hash`.

### Examples
- `examples/manifest/finance-agent-v2.json` gains populated `lifecycle` and `evaluation` blocks demonstrating a 4-transition path to production with three eval gates (regression, safety, latency).
- `overall_hash` of the example is **unchanged** — confirming lifecycle + evaluation correctly sit outside `contract`.

### 0.6.0 - 2026-05-12

### Added — Environment Fingerprint Surface (§3a)
- **New contract surface** `environment` on `AgentContract` with fields: `deployment_id`, `region`, `infra_image_hash`, `runtime_versions`, `secret_refs`, `external_service_pins`, `feature_flags`, `resource_limits`. All optional — older v0.5 manifests still validate.
- **`ResourceLimits` model** with `memory_mb`, `cpu_cores`, `timeout_seconds`, `max_concurrent_calls`.
- **JSON Schema** for the new block under `contract.environment`.
- **Diff classifier** `environment_severity()` with field-level severity rules:
  - `deployment_id`, `secret_refs`, `feature_flags`, `resource_limits` → minor
  - `region`, `infra_image_hash`, `runtime_versions`, `external_service_pins` → moderate
  - Environment changes are always classified `non_breaking` (they affect replayability, not validity of past traces).
- **New reason codes** in `compatibility_decision.reason_codes` enum: `region_changed`, `infra_image_changed`, `external_service_pin_changed`, `runtime_version_changed`. Plus the existing `environment_unreplayable` as a catch-all.
- **Condition tokens** `environment_surface_unchanged` / `environment_surface_changed` for `ClassificationRule.condition`.
- **`CompatibilityPolicy.environment`** for user-configurable rules on the new surface.
- **Spec doc** [`spec/environment.md`](./spec/environment.md) — full surface spec, field reference, severity rules, security notes, hash participation.
- **Example** `examples/manifest/finance-agent-v2.json` gains a populated `environment` block.
- 19 new tests in `tests/test_environment.py`.

### Security note
`environment.secret_refs` holds **names** (identifiers), not values. Implementations that put plaintext secrets there leak credentials into the manifest hash.

### 0.5.0 - 2026-05-12

### Added — Manifest References (§3c)
- **`agent_version_spec.refs` module** with `ManifestRef`, `parse_manifest_ref(s)`, `try_parse_manifest_ref(s)`, `is_bare_id_ref(s)`.
- **URI scheme** for `SubagentDescriptor.manifest_ref`:
  - `avs:manifest:<id>` — by-ID reference (registry resolution).
  - `avs:hash:<algo>:<hex>` — content-addressed (immutable).
  - `https://...` / `http://...` — fetchable URL.
  - `file:///path/manifest.json` — local file.
  - Bare `<id>` — implicit `avs:manifest:` (deprecated in v0.x; removed in v1.0).
- **JSON Schema** pattern on `subagents[].manifest_ref` accepts all five forms.
- **Validator** semantic rules: `malformed_manifest_ref` (ERROR), `bare_manifest_ref` (WARNING; ERROR under `--strict-ids`). Embedded IDs in `avs:manifest:` URIs run through the same ID checks as `manifest_id`.
- **Spec doc** [`spec/refs.md`](./spec/refs.md) — full URI scheme, resolution semantics, JSON Schema pattern, v0.x → v1.0 promise.
- Example `examples/manifest/finance-agent-v2.json` updated: bare-ID subagent refs (`amf_finance_subagent_v3`) → canonical URIs (`avs:manifest:amf_01KREPJH26…`); fixed `manifest_id` from a not-actually-Crockford-base32 placeholder to a real ULID; recomputed `identity.overall_hash`.
- 25 new tests in `tests/test_refs.py`.

### Added — Generalized ID Enforcement (§3b follow-up)
- **`check_object_ids(data, kind, strict)`** in `ids.py` validates every known ID field across **all** spec kinds (manifest, task, episode, step, dataset_snapshot, compatibility_decision, compatibility_batch, compatibility_report, replay_job, replay_result, manifest_diff).
- Walks dotted paths with `[]` array notation; handles `subject.id` specially (its expected prefix depends on `subject.type`).
- **CLI subcommands** `avs decision validate`, `avs replay validate`, `avs dataset validate` all gained `--strict-ids` and emit the same warning/error vocabulary as `avs validate`.
- 9 new tests covering non-manifest objects.

### Changed
- `validate_manifest()` now delegates its ID checks to `check_object_ids()` — single source of truth for ID rules.

### 0.4.0 - 2026-05-12

### Added — Canonical IDs (§3b)
- **`agent_version_spec.ids` module** with `mint_id(kind)`, `parse_id(s)`, `validate_id(s, expected_kind=None, strict=False)`, `is_canonical_id(s)`, `is_permissive_id(s)`, and the `ID_PREFIXES` map (12 known kinds).
- **Canonical ID form**: `<kind-prefix>_<26-char Crockford base32 ULID>` (e.g. `amf_01HZK1A2B3C4D5E6F7G8H9J0K1`). Sortable by mint time; one less character than UUID; type-prefixed for at-a-glance kind identification.
- **Permissive form** (v0.x back-compat): JSON Schema `pattern` accepts both canonical ULID and semantic-slug IDs (e.g. `amf_finance_v3`). The validator emits a `non_canonical_id` WARNING for slug IDs through the v0.x line.
- **Semantic validator rules** (`validator.py`):
  - `malformed_id` — ERROR when an ID matches neither canonical nor permissive form.
  - `wrong_id_prefix` — ERROR (or escalated WARNING) when an ID's prefix doesn't match the object's kind.
  - `non_canonical_id` — WARNING (or ERROR under `--strict-ids`) for slug IDs.
- **CLI**: `avs validate --strict-ids` escalates `non_canonical_id` warnings to errors. Matches the v1.0 behavior.
- **Spec doc**: [`spec/ids.md`](./spec/ids.md) documents the format, prefix table, rationale, API, and the v0.x → v1.0 tightening.
- 23 new tests in `tests/test_ids.py`.

### Changed
- `validate_manifest()` and `validate_manifest_file()` accept a `strict_ids: bool = False` keyword.

### Not yet enforced
- v1.0 will drop the permissive pattern. `non_canonical_id` becomes an error by default. Plan accordingly: tools that mint new IDs should produce canonical ULID form starting now.

### 0.3.0 - 2026-05-12

### Changed (breaking — nothing shipped publicly yet)
- **Renamed `rescue_decision` → `compatibility_decision`** (`RescueDecision` → `CompatibilityDecision`, schema file, kind, spec doc, CLI group). Aligns with the rest of the compatibility family.
- **Renamed `rescue_batch` → `compatibility_batch`** (`RescueBatch` → `CompatibilityBatch`, summary class, schema file, kind, spec doc).
- **Renamed `validators` surface → `guardrails`** (`ValidatorBundle` → `GuardrailBundle`). Removes naming collision with Pydantic and JSON-Schema validators.
- **Renamed schema file** `agent-version-spec.schema.json` → `agent-manifest.schema.json` to match the kind it defines.
- **Renamed module** `agent_version_spec/rescue.py` → `agent_version_spec/decision.py`.
- **CLI:** `avs rescue ...` → `avs decision ...` for both `validate` and `generate`.
- **Dropped** `validators.requires_confirmation_for_destructive_actions` — promote to per-tool `annotations.requires_confirmation` instead.
- **Renamed** `GuardrailBundle` fields: `validator_bundle_version` → `bundle_version`, `validator_bundle_hash` → `bundle_hash`.
- **Reason code** `validator_policy_changed` → `guardrail_policy_changed`; added `skill_missing`, `skill_content_changed`.
- **Condition tokens** `validator_surface_*` → `guardrail_surface_*`; added `skill_surface_unchanged` / `skill_surface_changed`.
- **Tool annotations** standardized to snake_case: `requiresConfirmation` → `requires_confirmation`, `readOnlyHint` → `read_only_hint`.

### Added
- **`skill_registry` contract surface** is now first-class: `SkillRegistry` + `SkillDescriptor` are in the JSON schema (`agent-manifest.schema.json`), reference spec, diff surface enum, compatibility-policy schema, and condition DSL. Previously code-only.
- **`compatibility-report.schema.json`** — JSON Schema for the `CompatibilityReport` output of `classify_compatibility()`. Closes the gap where the class existed but had no schema.
- `__version__` is now read from package metadata via `importlib.metadata`, eliminating the package-version / `__version__` drift bug.

### 0.2.0 - 2026-03-18

### Added
- `skill_registry` Pydantic model + diff classifier (informally; not yet in schemas — see 0.3.0).
- Quantized float hashing for `generation_config` (temperature step 0.1, top_p step 0.05) so micro-tweaks don't churn manifest hashes.
- New manifest fields: `status`, `capabilities`, `description`, tool-level `description` + `annotations`.
- `OutputContract.modalities`.
- `compatibility-policy.schema.json` — user-configurable rules mapping change severity to actions per surface.
- Formalized condition DSL for `ClassificationRule.condition` with `SURFACE_STATE_TOKENS` / `PARAMETERIZED_TOKENS` and a `validate_condition()` enforcer.

### 0.1.0 - 2026-03-11

### Added
- Initial public scaffolding of the Agent Version Spec.
- Spec documents, JSON Schemas, Pydantic models, JCS-SHA256 hasher, surface-level diff engine, compatibility classifier.
- CLI entry point (`avs`) with `validate`, `diff`, `hash`, `init`, `upgrade` and subcommand groups.
