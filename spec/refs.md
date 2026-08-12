# Manifest References

> Status: Stable v1.0 · Added in v0.5.0 · Tightened in v1.0
>
> Version numbers on this page are **spec** milestones (the on-the-wire `spec_version`), not the PyPI **package** version. The shipped `agentversion` package is still pre-1.0 while the spec is at 1.0 — see [versioning-policy.md](versioning-policy.md).

How fields like `subagents[].manifest_ref` point at other manifests. Defines a small URI scheme so the same field works for local lookups, content-addressed pins, and remote fetches.

## Why this exists

`SubagentDescriptor.manifest_ref` was previously a free-text string. That works inside one process but doesn't compose across registries — there's no way to tell whether `amf_finance_v3` is a local manifest ID, a slug, a path, or a URL. v0.5 fixes that by giving `manifest_ref` a typed URI scheme.

## Forms

| URI | Semantics | Use when |
|---|---|---|
| `agentversion:manifest:<manifest_id>` | Reference by ID. Resolution is implementation-defined (typically: look in a local registry indexed by manifest_id). | You and the consumer share a registry. |
| `agentversion:hash:<algo>:<hex>` | Content-addressed. The hash pins to a specific `identity.overall_hash`. | You need immutability — the ref will resolve to *exactly* this manifest contract or fail. |
| `https://...` / `http://...` | Fetchable URL pointing to a JSON manifest. | Cross-org reference; the consumer dereferences via HTTP. |
| `file:///abs/path/manifest.json` | Local filesystem path. | Local dev / monorepo workflows. |

## Examples

```json
{
  "subagents": [
    { "name": "finance", "manifest_ref": "agentversion:manifest:amf_01HZK1A2B3C4D5E6F7G8H9J0K1" },
    { "name": "billing", "manifest_ref": "agentversion:hash:sha256:d44595…" },
    { "name": "research", "manifest_ref": "https://registry.acme.dev/research-agent.json" },
    { "name": "fixture", "manifest_ref": "file:///opt/manifests/fixture-agent.json" }
  ]
}
```

## API

```python
from agentversion.refs import (
    ManifestRef,
    Scheme,
    parse_manifest_ref,
    try_parse_manifest_ref,
)

ref = parse_manifest_ref("agentversion:manifest:amf_01HZK1A2B3C4D5E6F7G8H9J0K1")
# ManifestRef(scheme="agentversion.manifest", manifest_id="amf_01HZK…")

ref.is_content_addressed()  # False — by ID, not by hash
ref.is_fetchable()           # False — needs registry context

ref = parse_manifest_ref("agentversion:hash:sha256:abc123…")
ref.is_content_addressed()  # True

ref = parse_manifest_ref("https://example.com/m.json")
ref.is_fetchable()           # True
```

`parse_manifest_ref` raises `ValueError` on unrecognized input. Use `try_parse_manifest_ref` to get `None` instead.

## JSON Schema

The `manifest_ref` field is constrained by this pattern in `schemas/agent-manifest.schema.json`:

```
^(agentversion:manifest:[a-z][a-z0-9]*_[0-9A-HJKMNP-TV-Z]{26}|agentversion:hash:[a-z0-9-]+:[A-Fa-f0-9]+|https?://.+|file://.+)$
```

The embedded ID in `agentversion:manifest:<id>` must itself be canonical (ULID form). The bare-ID form (a manifest ID with no `agentversion:manifest:` prefix) was removed in v1.0, so a bare ID no longer matches this pattern at all.

## Validator behavior

- **`malformed_manifest_ref`** (ERROR): the string doesn't match any recognized form. Because the bare-ID alternative was removed, a bare ID (e.g. `amf_01HZK…` with no scheme prefix) now fails here as malformed rather than passing with a warning.
- **Embedded ID checks**: when `agentversion:manifest:<id>` is used, the embedded ID is run through the same `validate_id` rules as `manifest_id` itself (malformed/wrong-prefix/non-canonical).

## Resolution (out of scope for v1.0)

This spec defines the format. It does **not** define how an implementation resolves a `ManifestRef` to an actual manifest. Reasonable strategies:

- For `agentversion:manifest:<id>`: look up the ID in a local registry table or filesystem index.
- For `agentversion:hash:<algo>:<hex>`: same, plus a content integrity check after retrieval.
- For `https://...`: fetch, parse, optionally verify Content-Type and signature.
- For `file://...`: read the file, parse.

A future revision (potentially v1.x or v2.0) may add a `Resolver` interface to the spec.
