"""Canonical IDs for AgentVersion.

Every spec object uses a type-prefixed identifier:

    <kind-prefix>_<26-char Crockford base32 ULID>

ULIDs (Universally Unique Lexicographically Sortable Identifiers) are
preferred over UUIDs because they're monotonic — IDs minted later sort
strictly after IDs minted earlier within the same millisecond, which means
``ORDER BY id`` is a valid ``ORDER BY created_at`` for most purposes.

Example: ``amf_01HZK1A2B3C4D5E6F7G8H9J0K1``

See [spec/ids.md](../spec/ids.md) for the full spec.
"""

from __future__ import annotations

import re
import secrets
import time
from typing import Any

# kind → ID prefix. Prefixes are short, type-distinctive, no collisions.
ID_PREFIXES: dict[str, str] = {
    "agent_manifest": "amf",
    "task": "tsk",
    "episode": "ep",
    "step": "stp",
    "dataset_snapshot": "dss",
    "compatibility_decision": "cdc",
    "compatibility_batch": "cbt",
    "compatibility_report": "cpr",
    "compatibility_policy": "cpl",
    "replay_job": "rpj",
    "replay_result": "rpr",
    "manifest_diff": "mdf",
}

# Crockford base32 alphabet: excludes I, L, O, U to avoid confusion with 1, 0.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Canonical ID pattern. The kind prefix is whatever's in ID_PREFIXES; we don't
# bake the list into the regex so adding a new kind doesn't require a regex
# change.
_ULID_BODY = r"[0-9A-HJKMNP-TV-Z]{26}"
_CANONICAL_ID_RE = re.compile(rf"^([a-z][a-z0-9]*)_({_ULID_BODY})$")


def _encode_crockford(value: int, length: int) -> str:
    """Encode an int into a fixed-length Crockford base32 string (big-endian)."""
    out: list[str] = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        out.append(_CROCKFORD[rem])
    return "".join(reversed(out))


def _new_ulid(now_ms: int | None = None) -> str:
    """Generate a new ULID as a 26-character Crockford base32 string.

    Format: 10 chars timestamp (48 bits) + 16 chars randomness (80 bits).
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    ts_part = _encode_crockford(now_ms & ((1 << 48) - 1), 10)
    rand_int = int.from_bytes(secrets.token_bytes(10), "big")
    rand_part = _encode_crockford(rand_int, 16)
    return ts_part + rand_part


def mint_id(kind: str) -> str:
    """Mint a new canonical ID for the given spec object kind.

    Args:
        kind: The object kind (e.g. ``"agent_manifest"``, ``"task"``).
            Must be a key in :data:`ID_PREFIXES`.

    Returns:
        A new ID in the form ``<prefix>_<ULID>``.

    Raises:
        ValueError: If ``kind`` is not a known spec kind.
    """
    try:
        prefix = ID_PREFIXES[kind]
    except KeyError as exc:
        known = ", ".join(sorted(ID_PREFIXES))
        raise ValueError(f"unknown kind {kind!r}; known kinds: {known}") from exc
    return f"{prefix}_{_new_ulid()}"


def parse_id(s: str) -> tuple[str, str] | None:
    """Parse a canonical ID into (prefix, ulid). Returns None if not canonical."""
    m = _CANONICAL_ID_RE.match(s)
    if not m:
        return None
    return m.group(1), m.group(2)


def is_canonical_id(s: str) -> bool:
    """True if ``s`` is in canonical ``<prefix>_<ULID>`` form."""
    return bool(_CANONICAL_ID_RE.match(s))


def validate_id(s: str, expected_kind: str | None = None) -> bool:
    """Validate an ID string.

    Args:
        s: The ID to validate.
        expected_kind: If supplied, also verify the prefix matches the prefix
            registered for this kind in :data:`ID_PREFIXES`.

    Returns:
        True if valid.

    Raises:
        ValueError: If the ID is not canonical or its prefix doesn't match
            ``expected_kind``.
    """
    if not s or not isinstance(s, str):
        raise ValueError(f"ID must be a non-empty string, got {type(s).__name__}")

    if not is_canonical_id(s):
        raise ValueError(
            f"ID {s!r} is not canonical. Required form: "
            f"'<prefix>_<26-char Crockford-base32 ULID>'."
        )

    if expected_kind is not None:
        prefix = ID_PREFIXES.get(expected_kind)
        if prefix is None:
            raise ValueError(f"unknown expected_kind {expected_kind!r}")
        actual_prefix = s.split("_", 1)[0]
        if actual_prefix != prefix:
            raise ValueError(
                f"ID {s!r} has prefix {actual_prefix!r} "
                f"but expected_kind={expected_kind!r} requires prefix {prefix!r}"
            )

    return True


# --- Field map for cross-object ID enforcement ---
#
# For each spec kind, a list of (path, expected_kind) pairs describing where
# IDs live. Paths use dotted notation; ``foo[]`` means "iterate the list at
# foo and apply the remainder to each element". Missing or null leaves are
# skipped silently.
_ID_FIELDS_BY_KIND: dict[str, list[tuple[str, str]]] = {
    "agent_manifest": [
        ("manifest_id", "agent_manifest"),
        ("parent_manifest_id", "agent_manifest"),
    ],
    "task": [
        ("task_id", "task"),
    ],
    "episode": [
        ("episode_id", "episode"),
        ("task_id", "task"),
        ("manifest_id", "agent_manifest"),
        ("lineage.parent_episode_id", "episode"),
    ],
    "step": [
        ("step_id", "step"),
        ("episode_id", "episode"),
    ],
    "dataset_snapshot": [
        ("snapshot_id", "dataset_snapshot"),
        ("item_refs[].task_id", "task"),
        ("item_refs[].episode_id", "episode"),
        ("item_refs[].step_id", "step"),
        ("lineage.source_snapshot_ids[]", "dataset_snapshot"),
        ("lineage.built_from_manifest_ids[]", "agent_manifest"),
    ],
    "compatibility_decision": [
        ("decision_id", "compatibility_decision"),
        ("old_manifest_id", "agent_manifest"),
        ("target_manifest_id", "agent_manifest"),
        # subject.id is checked separately — its expected kind depends on
        # subject.type. See check_object_ids().
    ],
    "compatibility_batch": [
        ("batch_id", "compatibility_batch"),
        ("old_manifest_id", "agent_manifest"),
        ("target_manifest_id", "agent_manifest"),
    ],
    "compatibility_report": [
        ("old_manifest_id", "agent_manifest"),
        ("new_manifest_id", "agent_manifest"),
    ],
    "replay_job": [
        ("replay_job_id", "replay_job"),
        ("task_id", "task"),
        ("source_episode_id", "episode"),
        ("target_manifest_id", "agent_manifest"),
        ("lineage.requested_from_episode_id", "episode"),
    ],
    "replay_result": [
        ("replay_job_id", "replay_job"),
        ("target_manifest_id", "agent_manifest"),
        ("replayed_episode_id", "episode"),
    ],
    "manifest_diff": [
        ("old_manifest_id", "agent_manifest"),
        ("new_manifest_id", "agent_manifest"),
    ],
}


def _walk_path(data: object, path: str) -> list[tuple[str, object]]:
    """Walk a dotted path with optional ``[]`` array suffix.

    Returns list of (concrete_path, value) for every reachable leaf. Missing
    intermediate keys → empty list. Null values → skipped.
    """
    if not isinstance(data, dict):
        return []
    current: list[tuple[str, object]] = [("", data)]
    for part in path.split("."):
        is_array = part.endswith("[]")
        key = part[:-2] if is_array else part
        next_set: list[tuple[str, object]] = []
        for prefix, val in current:
            if not isinstance(val, dict):
                continue
            child = val.get(key)
            if child is None:
                continue
            new_prefix = f"{prefix}.{key}" if prefix else key
            if is_array:
                if isinstance(child, list):
                    for i, item in enumerate(child):
                        if item is None:
                            continue
                        next_set.append((f"{new_prefix}[{i}]", item))
            else:
                next_set.append((new_prefix, child))
        current = next_set
    return current


# Issue tuple: (severity_str, code, message, path)
IdIssue = tuple[str, str, str, str]


def _check_one_id(
    value: object,
    expected_kind: str,
    path: str,
) -> IdIssue | None:
    """Validate one ID value. Returns one issue or None."""
    if not isinstance(value, str):
        return None
    expected_prefix = ID_PREFIXES.get(expected_kind, "")

    if not is_canonical_id(value):
        return (
            "error",
            "malformed_id",
            f"{path}={value!r} is not canonical. Required form: "
            f"'{expected_prefix}_<26-char Crockford-base32 ULID>'.",
            path,
        )

    actual_prefix = value.split("_", 1)[0]
    if actual_prefix != expected_prefix:
        return (
            "error",
            "wrong_id_prefix",
            f"{path}={value!r} has prefix {actual_prefix!r}, "
            f"expected {expected_prefix!r} for kind {expected_kind!r}",
            path,
        )
    return None


def check_object_ids(data: dict[str, Any], kind: str | None = None) -> list[IdIssue]:
    """Validate every known ID field on a spec object.

    Args:
        data: The parsed JSON object.
        kind: The spec kind (``"agent_manifest"``, ``"task"``, etc). If None,
            uses ``data["kind"]``. Unknown kinds return an empty list.

    Returns:
        A list of ``(severity, code, message, path)`` tuples.
    """
    if kind is None:
        kind = data.get("kind") if isinstance(data, dict) else None
    if not kind or kind not in _ID_FIELDS_BY_KIND:
        return []

    issues: list[IdIssue] = []
    for path_spec, expected_kind in _ID_FIELDS_BY_KIND[kind]:
        for concrete_path, value in _walk_path(data, path_spec):
            issue = _check_one_id(value, expected_kind, concrete_path)
            if issue is not None:
                issues.append(issue)

    # subject.id's expected prefix depends on subject.type
    if kind == "compatibility_decision":
        subject = data.get("subject") if isinstance(data, dict) else None
        if isinstance(subject, dict):
            sub_type = subject.get("type")
            sub_id = subject.get("id")
            if isinstance(sub_type, str) and isinstance(sub_id, str):
                if sub_type in ID_PREFIXES:
                    issue = _check_one_id(sub_id, sub_type, "subject.id")
                    if issue is not None:
                        issues.append(issue)
                elif not sub_id.strip():
                    # Subject types without a registered ID prefix (e.g.
                    # dataset_item) have no canonical-prefix contract, but the
                    # id must still be a non-empty string — otherwise a subject
                    # could carry a blank/garbage id and pass silently.
                    issues.append(
                        (
                            "error",
                            "empty_id",
                            f"subject.id is empty for subject.type {sub_type!r}",
                            "subject.id",
                        )
                    )

    return issues


__all__ = [
    "ID_PREFIXES",
    "IdIssue",
    "check_object_ids",
    "is_canonical_id",
    "mint_id",
    "parse_id",
    "validate_id",
]
