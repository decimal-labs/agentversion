"""Canonical hashing for AgentVersion.

Implements JCS-SHA256 (RFC 8785 + SHA-256) for deterministic,
reproducible manifest hashing.

See spec/reference.md §10 for the algorithm specification.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from typing import Any

from jcs import canonicalize


def _normalize_for_hash(obj: Any) -> Any:
    """Make a value safe + deterministic for canonical hashing across implementations.

    JCS (RFC 8785) canonicalizes *bytes* but does NOT Unicode-normalize, and has no representation for
    non-finite floats — both break the byte-identical, cross-language reproduction the overall_hash
    (the moat) promises. So before canonicalizing we:

    * **NFC-normalize every string** (keys and values). Otherwise a composed ``"café"`` (U+00E9) and a
      decomposed ``"café"`` (U+0065 U+0301) produce different UTF-8 bytes → different ``overall_hash``
      for two semantically identical manifests. A producer on a different OS/keyboard/normalization
      regime would mint a different identity for the same agent.
    * **Reject NaN / ±Infinity.** They have no canonical-JSON form, so a manifest carrying one is
      malformed; fail with a stable, descriptive error instead of an opaque ``jcs`` ``ValueError`` or a
      platform-dependent hash. (``bool`` is left as-is — it is an ``int`` subclass, not a float.)
    """
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(
                f"non-finite float {obj!r} cannot be canonically hashed — a manifest must not carry "
                "NaN or Infinity (they have no canonical-JSON representation)"
            )
        return obj
    if isinstance(obj, dict):
        return {
            (unicodedata.normalize("NFC", k) if isinstance(k, str) else k): _normalize_for_hash(v)
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [_normalize_for_hash(v) for v in obj]
    return obj

# --- Quantized float hashing ---

# Inline runtime knobs that some producers flatten into model_runtime or
# generation_config (e.g. SDK retry/timeout settings). They don't affect the
# agent's logical contract, so they're stripped before hashing to keep identity
# stable. This targets raw producer dicts — validated manifests never carry
# these (pydantic drops unknown fields), while the *structured* envelope
# (cost / rate_limit) and environment.resource_limits are part of the hash by design.
_RUNTIME_ONLY_KEYS = frozenset({"max_retries", "timeout", "rate_limit", "batch_size"})

# Quantization steps per parameter
_QUANTIZE_STEPS: dict[str, float] = {
    "temperature": 0.1,
    "top_p": 0.05,
}


def quantize_float(value: float | None, step: float = 0.1) -> float | None:
    """Quantize a float to the nearest step for threshold-based hashing.

    Small numeric tweaks don't create new versions:
    - temperature 0.71 → 0.7 (same hash), 0.8 → 0.8 (new hash)
    - top_p 0.92 → 0.90, 0.95 → 0.95

    Returns None if input is None.
    """
    if value is None:
        return None
    # Round to step precision, then round to 10 decimal places to avoid
    # IEEE 754 floating point artifacts (e.g. 0.7000000000000001)
    return round(round(value / step) * step, 10)


def _quantize_generation_config(gen_config: dict[str, Any]) -> dict[str, Any]:
    """Quantize generation_config params and strip runtime-only keys.

    Returns a new dict suitable for hashing (original is not modified).
    """
    result = {}
    for key, value in gen_config.items():
        if key in _RUNTIME_ONLY_KEYS:
            continue
        if key in _QUANTIZE_STEPS and isinstance(value, (int, float)):
            result[key] = quantize_float(float(value), _QUANTIZE_STEPS[key])
        else:
            result[key] = value
    return result


def prepare_surface_for_hashing(
    surface_name: str, surface_data: dict[str, Any]
) -> dict[str, Any]:
    """Prepare a contract surface for hashing.

    Shared canonicalization primitive: both ``hash_manifest`` and the diff
    engine's surface-equality quick-check route through this so the two agree
    on what counts as a change (see ``diff.diff_manifests``).

    For ``model_runtime``, quantizes generation_config floats and strips
    runtime-only keys so that small tweaks don't cause hash churn.

    For all other surfaces, returns the data unchanged.
    """
    if surface_name != "model_runtime":
        # All other surfaces (including skill_registry) are hashed as-is.
        # skill_registry: no quantization needed; the hash changes only when
        # skills are added, removed, or their content hashes change.
        return surface_data

    result = {}
    for key, value in surface_data.items():
        if key in _RUNTIME_ONLY_KEYS:
            continue
        elif key == "generation_config" and isinstance(value, dict):
            result[key] = _quantize_generation_config(value)
        else:
            result[key] = value
    return result


def hash_surface(surface_data: dict[str, Any]) -> str:
    """Compute the canonical hash of a single contract surface.

    Args:
        surface_data: The dict for one contract surface (e.g. prompt_stack).

    Returns:
        Hash string in the format ``sha256:<hex digest>``.
    """
    canonical = canonicalize(_normalize_for_hash(surface_data))
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def hash_manifest(manifest_data: dict[str, Any]) -> str:
    """Compute the overall_hash from a manifest's contract block.

    The overall hash is derived **only** from the contract block, not from
    metadata (tags, description, created_at, etc.). This ensures two manifests
    with identical contracts produce identical identity hashes.

    For ``model_runtime``, generation_config floats are quantized before
    hashing so that small tweaks (temperature 0.71 → 0.7) don't cause
    version churn.

    Algorithm:
        1. Extract the ``contract`` block
        2. For each surface key (sorted alphabetically):
           a. Prepare the surface (quantize floats for model_runtime)
           b. Compute ``hash_surface()``
        3. Concatenate ``"key=hash\\n"`` for each surface
        4. SHA-256 the concatenation

    Args:
        manifest_data: Full manifest as a dict with a ``contract`` key.

    Returns:
        Hash string in the format ``sha256:<hex digest>``.

    Raises:
        KeyError: If ``contract`` key is missing from manifest_data.
    """
    contract = manifest_data["contract"]
    surface_hashes = []
    for key in sorted(contract.keys()):
        prepared = prepare_surface_for_hashing(key, contract[key])
        surface_hashes.append(f"{key}={hash_surface(prepared)}")
    combined = "\n".join(surface_hashes)
    return f"sha256:{hashlib.sha256(combined.encode('utf-8')).hexdigest()}"


def compute_and_set_hashes(manifest_data: dict[str, Any]) -> dict[str, Any]:
    """Compute and populate all hashes on a manifest dict in-place.

    Sets ``identity.overall_hash`` and ``identity.hash_algorithm``.

    Args:
        manifest_data: Full manifest dict. Modified in-place.

    Returns:
        The same manifest dict with hashes populated.
    """
    overall = hash_manifest(manifest_data)
    if "identity" not in manifest_data:
        manifest_data["identity"] = {}
    manifest_data["identity"]["overall_hash"] = overall
    manifest_data["identity"]["hash_algorithm"] = "jcs-sha256"
    return manifest_data
