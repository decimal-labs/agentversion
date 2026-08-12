"""Typed references to manifests (and other spec objects).

Today the only consumer is ``SubagentDescriptor.manifest_ref``, but the same
URI scheme generalizes to dataset / replay references.

## Recognized forms

| URI                                  | Semantics                          |
|--------------------------------------|------------------------------------|
| ``agentversion:manifest:<manifest_id>``       | Reference by ID. Resolution is implementation-defined (typically: look in a local registry). |
| ``agentversion:hash:<algo>:<hex>``            | Content-addressed (immutable). Algorithm is usually ``sha256``. |
| ``https://...`` / ``http://...``     | Fetchable URL pointing to JSON manifest. |
| ``file:///abs/path/manifest.json``   | Local filesystem reference. |

## API

>>> from agentversion.refs import parse_manifest_ref
>>> r = parse_manifest_ref("agentversion:manifest:amf_01HZK1A2B3C4D5E6F7G8H9J0K1")
>>> r.scheme
'agentversion.manifest'
>>> r.manifest_id
'amf_01HZK1A2B3C4D5E6F7G8H9J0K1'

>>> r = parse_manifest_ref("agentversion:hash:sha256:abcdef0123456789")
>>> r.is_content_addressed()
True

See [spec/refs.md](../spec/refs.md) for the full spec.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from agentversion.ids import validate_id

_MANIFEST_RE = re.compile(r"^agentversion:manifest:(.+)$")
_HASH_RE = re.compile(r"^agentversion:hash:([a-z0-9-]+):([A-Fa-f0-9]+)$")
_HTTPS_RE = re.compile(r"^(https?)://(.+)$")
_FILE_RE = re.compile(r"^file://(.+)$")

Scheme = Literal["agentversion.manifest", "agentversion.hash", "http", "https", "file"]


class ManifestRef(BaseModel):
    """A parsed manifest reference.

    Exactly one of ``manifest_id``, ``hash``, ``url``, ``path`` is set
    depending on ``scheme``. ``raw`` always carries the original string for
    round-tripping.
    """

    raw: str
    scheme: Scheme

    manifest_id: str | None = None
    hash: str | None = None
    url: str | None = None
    path: str | None = None

    def is_content_addressed(self) -> bool:
        """True if this ref pins to a specific content hash (verifiable)."""
        return self.scheme == "agentversion.hash"

    def is_fetchable(self) -> bool:
        """True if a resolver can dereference this without registry context."""
        return self.scheme in ("http", "https", "file")


def parse_manifest_ref(s: str) -> ManifestRef:
    """Parse a manifest reference string into a typed ``ManifestRef``.

    Args:
        s: The reference string.

    Returns:
        A populated ``ManifestRef``.

    Raises:
        ValueError: If ``s`` doesn't match any recognized scheme. The error
            message lists the accepted forms.
    """
    if not isinstance(s, str) or not s:
        raise ValueError(f"manifest ref must be a non-empty string, got {type(s).__name__}")

    m = _MANIFEST_RE.match(s)
    if m:
        manifest_id = m.group(1)
        validate_id(manifest_id, expected_kind="agent_manifest")
        return ManifestRef(raw=s, scheme="agentversion.manifest", manifest_id=manifest_id)

    m = _HASH_RE.match(s)
    if m:
        algo, hexdigest = m.group(1), m.group(2)
        return ManifestRef(raw=s, scheme="agentversion.hash", hash=f"{algo}:{hexdigest}")

    m = _HTTPS_RE.match(s)
    if m:
        proto = m.group(1)  # "http" or "https"
        return ManifestRef(raw=s, scheme=proto, url=s)  # type: ignore[arg-type]

    m = _FILE_RE.match(s)
    if m:
        return ManifestRef(raw=s, scheme="file", path=m.group(1))

    raise ValueError(
        f"manifest ref {s!r} doesn't match any recognized scheme. Accepted: "
        f"'agentversion:manifest:<id>', 'agentversion:hash:<algo>:<hex>', 'https://...', 'file://...'."
    )


def try_parse_manifest_ref(s: str) -> ManifestRef | None:
    """Parse a manifest reference, returning ``None`` on failure."""
    try:
        return parse_manifest_ref(s)
    except ValueError:
        return None


__all__ = [
    "ManifestRef",
    "Scheme",
    "parse_manifest_ref",
    "try_parse_manifest_ref",
]
