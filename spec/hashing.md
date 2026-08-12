# Canonical Hashing Algorithm

> Status: Stable v1.0 · Added in v0.1.0

See also [diff.md](./diff.md) and [versioning-policy.md](./versioning-policy.md).

The `identity.overall_hash` must be **reproducible** across implementations. This requires a deterministic normalization + hash pipeline.

## Algorithm: JCS-SHA256

1. **Pre-normalization (required for cross-language reproduction):**
   - **Unicode:** NFC-normalize every JSON string — object keys *and* string values, recursively.
     RFC 8785 canonicalizes *bytes* but does **not** Unicode-normalize, so a composed `"café"` (U+00E9)
     and a decomposed `"café"` (U+0065 U+0301) would otherwise produce different UTF-8 bytes and thus a
     different `overall_hash` for the same agent. A conforming implementation MUST apply Unicode NFC
     before canonicalization.
   - **Float domain:** a manifest MUST NOT carry a non-finite float (`NaN`, `+Infinity`, `-Infinity`).
     These have no representation in canonical JSON (RFC 8785 / ECMAScript number serialization). An
     implementation MUST reject such a manifest with an error rather than producing a hash. (Booleans
     are not floats.) Negative zero (`-0.0`) serializes as `0` per RFC 8785.
2. **Surface preparation (`model_runtime` only):** Before canonicalizing the
   `model_runtime` surface, an implementation MUST:
   - **Quantize generation-config floats** so sub-quantum noise doesn't churn the
     hash: `temperature` snaps to a step of `0.1` (e.g. `0.71 → 0.7`), `top_p` to a
     step of `0.05` (e.g. `0.92 → 0.90`).
   - **Strip runtime-only keys** that don't affect agent behavior:
     `max_retries`, `timeout`, `rate_limit`, `batch_size`.

   All other surfaces (including `skill_registry`) are hashed as-is. This step matches
   `hasher.prepare_surface_for_hashing`; omitting it produces a different `overall_hash`
   for the same logical agent when temperature carries floating-point noise.
3. **Canonicalization:** Apply [RFC 8785 (JSON Canonicalization Scheme)](https://www.rfc-editor.org/rfc/rfc8785) to the NFC-normalized, prepared input
4. **Hash function:** SHA-256
5. **Output format:** `sha256:<hex digest>`

NFC of pure-ASCII text is a no-op, so existing ASCII manifest hashes are unaffected by the
normalization step.

## Per-surface hashing

Each contract surface is hashed independently:

```python
def prepare_surface_for_hashing(surface_name: str, surface_data: dict) -> dict:
    """Quantize generation_config floats + strip runtime-only keys for model_runtime."""
    if surface_name != "model_runtime":
        return surface_data  # all other surfaces (incl. skill_registry) hashed as-is
    out = {}
    for key, value in surface_data.items():
        if key in {"max_retries", "timeout", "rate_limit", "batch_size"}:
            continue  # runtime-only, excluded from hash
        elif key == "generation_config" and isinstance(value, dict):
            out[key] = _quantize_generation_config(value)  # temperature→0.1, top_p→0.05
        else:
            out[key] = value
    return out


def hash_surface(surface_data: dict) -> str:
    """Canonical hash of a single (already-prepared) contract surface."""
    from jcs import canonicalize
    import hashlib
    # NFC-normalize strings + reject non-finite floats BEFORE canonicalizing (see Algorithm step 1).
    canonical = canonicalize(_normalize_for_hash(surface_data))  # RFC 8785
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"
```

## Overall hash computation

The `overall_hash` is derived **only from the contract block**, not from metadata (tags, description, created_at). This ensures two manifests with identical contracts produce identical identity hashes.

```python
def hash_manifest(manifest: dict) -> str:
    """Compute overall_hash from contract surfaces.

    1. Extract the `contract` block
    2. For each surface key (sorted alphabetically):
       a. Prepare the surface (quantize floats / strip runtime keys for model_runtime)
       b. Compute hash_surface()
    3. Concatenate: "key=hash\n" for each surface
    4. SHA-256 the concatenation
    """
    contract = manifest["contract"]
    surface_hashes = []
    for key in sorted(contract.keys()):
        prepared = prepare_surface_for_hashing(key, contract[key])
        surface_hashes.append(f"{key}={hash_surface(prepared)}")
    combined = "\n".join(surface_hashes)
    return f"sha256:{hashlib.sha256(combined.encode('utf-8')).hexdigest()}"
```

## What is NOT included in the hash

| Field | Reason |
|---|---|
| `manifest_id` | Generated ID, not content |
| `agent_name`, `agent_namespace` | Organizational metadata |
| `version_label` | Human-readable label |
| `created_at`, `created_by` | Timestamp/authorship metadata |
| `parent_manifest_id` | Lineage metadata |
| `description`, `tags` | Documentation metadata |
| `extensions` | Optional/custom metadata |

## `hash_algorithm` field

The `identity.hash_algorithm` field declares which algorithm was used. The only supported value is `"jcs-sha256"`. Future versions may support additional algorithms.
