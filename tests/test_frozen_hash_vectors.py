"""Frozen-vector anti-drift test for the manifest-aware versioning moat.

The other example-hash test (``test_example_manifests_have_correct_hashes`` in
``test_hasher.py``) is *self-referential*: it reads ``overall_hash`` from a
manifest and compares it to ``hash_manifest(manifest)`` recomputed by the same
code. A canonicalization or quantization change that altered *all* hashes the
same way would pass that test silently.

This test pins ``hash_manifest`` to LITERAL hash strings stored in
``tests/fixtures/frozen_hash_vectors.json``. Those literals were computed ONCE
by the current pipeline and do **not** flow through the code under test, so an
accidental drift in canonicalization (jcs upgrade), quantization steps, or the
surface-concatenation format is caught here.

================================ READ ME ===============================
IF THIS TEST FAILS: the hash output changed. That is a BREAKING change to the
moat -- every previously-stored ``overall_hash`` would stop reproducing, and
manifest identity / dataset validity across the platform would silently break.

Do NOT regenerate the vectors just to make the test green. Either:
  1. revert the change that altered the hash, or
  2. if the algorithm change is deliberate, treat it as an intentional breaking
     release: bump the hash/format version (``identity.hash_algorithm``,
     currently ``"jcs-sha256"`` -- see spec/hashing.md) and regenerate these
     vectors as part of that release.

To regenerate intentionally, run from the repo root:

    .venv/bin/python - <<'PY'
    import json
    from pathlib import Path
    from agentversion.hasher import hash_manifest
    p = Path("tests/fixtures/frozen_hash_vectors.json")
    doc = json.loads(p.read_text())
    for v in doc["vectors"].values():
        v["overall_hash"] = hash_manifest(v["input"])
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    PY
========================================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentversion.hasher import hash_manifest

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "frozen_hash_vectors.json"


def _load_vectors() -> dict[str, dict]:
    doc = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return doc["vectors"]


_VECTORS = _load_vectors()


def test_fixture_loaded_and_nonempty() -> None:
    """Guard against a silently-empty fixture making the parametrized test vacuous."""
    assert len(_VECTORS) >= 5, "expected at least 5 frozen hash vectors"


@pytest.mark.parametrize("name", sorted(_VECTORS), ids=sorted(_VECTORS))
def test_frozen_overall_hash(name: str) -> None:
    """``hash_manifest(input)`` must still equal the frozen literal.

    See the module docstring: a failure here is a BREAKING change to the hash
    algorithm, not something to paper over by regenerating the vector.
    """
    vector = _VECTORS[name]
    frozen = vector["overall_hash"]
    computed = hash_manifest(vector["input"])
    assert computed == frozen, (
        f"\nFROZEN HASH DRIFT for vector {name!r}:"
        f"\n  frozen  : {frozen}"
        f"\n  computed: {computed}"
        f"\nThe hashing pipeline changed. This is a BREAKING change to the moat -- "
        f"do NOT just regenerate the vector. See the module docstring."
    )
