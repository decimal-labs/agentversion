# Canonical IDs

> Status: Stable v1.0 · Added in v0.4.0 · Tightened in v1.0

How every spec object — manifests, tasks, episodes, steps, decisions, jobs — gets a stable identifier.

## Canonical form

```
<kind-prefix>_<26-char Crockford-base32 ULID>
```

Example: `amf_01HZK1A2B3C4D5E6F7G8H9J0K1`

The prefix tells you what kind of object you're looking at without having to read the surrounding context. The ULID portion sorts lexicographically by mint millisecond, so `ORDER BY id` approximates `ORDER BY created_at`; ordering *within* a single millisecond is not guaranteed (see "Why ULID, not UUID?" below).

## Prefixes

| Kind | Prefix | Example |
|---|---|---|
| `agent_manifest` | `amf` | `amf_01HZK1A2B3C4D5E6F7G8H9J0K1` |
| `task` | `tsk` | `tsk_01HZK1A2B3C4D5E6F7G8H9J0K2` |
| `episode` | `ep` | `ep_01HZK1A2B3C4D5E6F7G8H9J0K3` |
| `step` | `stp` | `stp_01HZK1A2B3C4D5E6F7G8H9J0K4` |
| `dataset_snapshot` | `dss` | `dss_01HZK1A2B3C4D5E6F7G8H9J0K5` |
| `compatibility_decision` | `cdc` | `cdc_01HZK1A2B3C4D5E6F7G8H9J0K6` |
| `compatibility_batch` | `cbt` | `cbt_01HZK1A2B3C4D5E6F7G8H9J0K7` |
| `compatibility_report` | `cpr` | `cpr_01HZK1A2B3C4D5E6F7G8H9J0K8` |
| `compatibility_policy` | `cpl` | `cpl_01HZK1A2B3C4D5E6F7G8H9J0K9` |
| `replay_job` | `rpj` | `rpj_01HZK1A2B3C4D5E6F7G8H9J0KA` |
| `replay_result` | `rpr` | `rpr_01HZK1A2B3C4D5E6F7G8H9J0KB` |
| `manifest_diff` | `mdf` | `mdf_01HZK1A2B3C4D5E6F7G8H9J0KC` |

Source of truth: `agentversion.ids.ID_PREFIXES`.

## Why ULID, not UUID?

A ULID is a 128-bit identifier with the same uniqueness guarantees as a UUIDv4, but encoded as 26 sortable characters instead of 36 unsortable ones. The first 48 bits are a millisecond timestamp; the remaining 80 bits are random. Within a millisecond, the random bits may be incremented to preserve monotonicity, though this implementation simply re-randomizes.

| Property | ULID | UUIDv4 |
|---|---|---|
| Sortable by mint time | ✅ | ❌ |
| Length when encoded | 26 chars | 36 chars |
| Collision probability (same ms) | ≈ 2⁻⁸⁰ | ≈ 2⁻¹²⁸ |
| Suitable for primary keys | ✅ | ✅ |
| Cryptographically random | partial (80 bits) | fully (122 bits) |

ULIDs are not appropriate where unguessability is a security property; for those cases, embed a separate token. They are appropriate for ordinary object identity.

## Only canonical form is accepted

Anything else — slugs, missing prefix, wrong-length ULID, lowercase Crockford alphabet — is rejected by the JSON Schema and the semantic validator alike. There is no permissive mode.

The validator emits two codes:

- **`malformed_id` (ERROR)** — the string doesn't match the canonical form.
- **`wrong_id_prefix` (ERROR)** — the string is canonical but its prefix doesn't match the kind of object that field belongs to (e.g. `amf_…` in a `task_id` slot).

## API

```python
from agentversion.ids import (
    ID_PREFIXES,
    mint_id,
    parse_id,
    validate_id,
    is_canonical_id,
)

mint_id("agent_manifest")
# → "amf_01KRENHVFPNWCVW296NGCG7FA5"

parse_id("amf_01KRENHVFPNWCVW296NGCG7FA5")
# → ("amf", "01KRENHVFPNWCVW296NGCG7FA5")

parse_id("amf_finance_v3")
# → None  (slug form is not canonical)

is_canonical_id("amf_finance_v3")
# → False

validate_id("amf_01KRENHVFPNWCVW296NGCG7FA5", expected_kind="agent_manifest")
# → True

validate_id("amf_finance_v3")
# → raises ValueError (not canonical)

validate_id("amf_01HZK1A2B3C4D5E6F7G8H9J0K1", expected_kind="task")
# → raises ValueError (wrong prefix)
```

## CLI

```bash
agentversion validate manifest.json
```

Non-canonical IDs are errors. There is no permissive mode.

## Foreign references

Fields like `parent_manifest_id`, `target_manifest_id`, `source_episode_id`, `built_from_manifest_ids[]` follow the same rules — their prefix must match the kind they reference. The reference validator enforces the prefix.

`subagents[].manifest_ref` is a special case: it may be a manifest_id **or** a URI (see [spec/manifest.md](manifest.md) §subagents). The URI form is specified separately and is allowed to omit the prefix when it identifies the kind via the URI scheme.
