# Versioning Policy

> Status: Stable v1.0 · Locked in v1.0

The AgentVersion follows [Semantic Versioning 2.0.0](https://semver.org/). Post-1.0, the policy below is a contract: implementations that adhere to the spec can rely on these guarantees.

## Spec version semantics

| Version range | Stability | What can change |
|---|---|---|
| `0.x.y` | unstable (now historical) | Anything could change between minor versions. See the CHANGELOG for what landed where. |
| `1.0.x` (patch) | **stable** | Bug fixes only. No field additions, no enum changes, no behavior changes. |
| `1.x.0` (minor) | **stable** | New optional fields. New enum values added (to open enums). New `kind` values for new spec objects. New `$defs` in JSON Schemas. Always backward-compatible — any v1.0 manifest validates under v1.x. |
| `x.0.0` (major) | **stable but breaking** | Removing fields, renaming fields, making optional fields required, changing field types, removing enum values, changing the hashing algorithm. Always documented in `CHANGELOG.md` with a migration path. |

## Rules for v1.x minor bumps

**Allowed (no version bump required for these):**
- Adding new optional fields to existing models / schemas
- Adding new values to enums explicitly marked as "open" (`step_type`, `reason_code`). These are still JSON-Schema-enumerated: the `enum` lists the *current* members and is extended (republished) in the same minor release. "Open" means the set may grow across minor versions, not that validators accept arbitrary strings.
- Adding new `kind` values for new spec objects
- Adding new `$defs` to JSON Schemas
- Adding new CLI subcommands
- Adding new validator codes (warnings or errors on previously-unchecked conditions)
- Tightening behavior of existing fields *only* if the previous behavior was clearly documented as "may change in a minor bump"

**Requires a major version bump:**
- Removing any field from a Pydantic model or JSON Schema
- Making an existing optional field required
- Changing a field's type
- Renaming a field (in JSON; Python aliases are allowed)
- Changing the canonical hashing algorithm
- Removing enum values from a closed enum
- Tightening regex patterns or other constraints in a way that rejects previously-valid inputs (this is what v1.0 itself did with the ID pattern — and was reserved for the major bump for that reason)
- Changing `kind` literal values

## Migration support

The reference implementation ships an `upgrade` CLI for low-cost migrations across minor versions and (with manual review) across majors:

```bash
agentversion upgrade old-manifest.json --to 1.2.0
agentversion validate manifest.json  # structural + semantic checks (version-agnostic within v1.x)
```

Within a major version, `upgrade` is an identity passthrough (no schema changes are required): it parses the manifest, sets `spec_version`, and re-emits. Cross-major upgrades are **not** performed automatically — the CLI refuses them and exits non-zero, pointing you to the CHANGELOG migration path (it also refuses downgrades).

> Note: the versions on this page are **spec** versions — the on-the-wire `spec_version`, frozen at `1.0.0`. They are independent of the PyPI **package** version, which is still pre-1.0 and moves on its own cadence. `pip show agentversion` reporting a lower number than this page does not make the page stale.

## v1.0 is the floor

v1.0 is the first stable release. There is no v0.x compatibility mode: anything before v1.0 was internal development and never shipped publicly.

The capability roadmap is complete; the spec is feature-stable. Future evolution follows the rules above.

## Stability of the conformance suite

The `compatibility-tests/` directory is the authoritative compliance gate. From v1.0 onward:

- Existing scenarios are **frozen** — the expected diffs in each `expected-diff.json` won't change in patch or minor releases.
- New scenarios may be added in minor releases. Implementations passing the v1.0.0 suite may not pass v1.3.0 if 1.3.0 added scenarios they don't cover; this is expected.
- Removing scenarios requires a major bump.

An implementation in any language can claim "conforming to AgentVersion 1.x" by passing the entire scenario suite of version 1.x or later. Conformance does not require Python, Pydantic, or any specific runtime.
