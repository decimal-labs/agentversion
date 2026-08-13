"""Conformance tests.

Each scenario under ``compatibility-tests/<name>/`` is a triple:
  before.json, after.json, expected-diff.json

A conforming implementation of the diff engine must, given the two manifests,
produce a ManifestDiff whose `changed_surfaces` and `summary` match the
expected output exactly (modulo ordering inside the lists).

This is the suite called out in the README's "Conformance tests" section.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentversion.diff import diff_manifests
from agentversion.hasher import hash_manifest
from agentversion.ids import is_canonical_id
from agentversion.validator import Severity, validate_manifest

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "compatibility-tests"


def _scenarios():
    """Yield every scenario directory that has all three files."""
    if not SCENARIO_DIR.is_dir():
        return
    for d in sorted(SCENARIO_DIR.iterdir()):
        if not d.is_dir():
            continue
        before = d / "before.json"
        after = d / "after.json"
        expected = d / "expected-diff.json"
        if before.is_file() and after.is_file() and expected.is_file():
            yield pytest.param(d, id=d.name)


@pytest.mark.parametrize("scenario_dir", list(_scenarios()))
def test_diff_matches_expected(scenario_dir: Path) -> None:
    before = json.loads((scenario_dir / "before.json").read_text())
    after = json.loads((scenario_dir / "after.json").read_text())
    expected = json.loads((scenario_dir / "expected-diff.json").read_text())

    actual = json.loads(diff_manifests(before, after).model_dump_json())

    assert actual["kind"] == "manifest_diff"
    assert actual["old_manifest_id"] == expected["old_manifest_id"]
    assert actual["new_manifest_id"] == expected["new_manifest_id"]

    # Compare changed_surfaces as a set keyed on (surface, change_type, severity).
    def _key(c: dict) -> tuple:
        return (c["surface"], c["change_type"], c.get("severity", "minor"))

    assert {_key(c) for c in actual["changed_surfaces"]} == {
        _key(c) for c in expected["changed_surfaces"]
    }, (
        f"\nactual surfaces:   {sorted(_key(c) for c in actual['changed_surfaces'])}"
        f"\nexpected surfaces: {sorted(_key(c) for c in expected['changed_surfaces'])}"
    )

    assert actual["summary"]["breaking_surfaces"] == expected["summary"]["breaking_surfaces"]
    assert (
        actual["summary"]["non_breaking_surfaces"]
        == expected["summary"]["non_breaking_surfaces"]
    )


# --- The corpus must satisfy the spec it is the gate for -------------------
#
# The golden fixtures are what another language's implementation reads to prove
# conformance, so a fixture that the repo's own schema and validator reject is
# worse than no fixture: it teaches the wrong thing. Two defects were shipped
# in the corpus and these tests are the guard against their return:
#   1. every manifest carried the v0.x permissive id form (amf_v1 / amf_v2),
#      which schemas/agent-manifest.schema.json rejects (removed in v1.0);
#   2. ten of the sixteen manifests declared the placeholder identity hash
#      "sha256:base", so the reference validator emitted WARNING hash_mismatch
#      on the reference corpus.


def _manifest_files():
    for d in sorted(SCENARIO_DIR.iterdir()) if SCENARIO_DIR.is_dir() else []:
        if not d.is_dir():
            continue
        for name in ("before.json", "after.json"):
            p = d / name
            if p.is_file():
                yield pytest.param(p, id=f"{d.name}/{name}")


@pytest.mark.parametrize("manifest_path", list(_manifest_files()))
def test_fixture_manifest_ids_are_canonical(manifest_path: Path) -> None:
    """Every fixture id is '<prefix>_<26-char Crockford ULID>', not a v0.x slug."""
    data = json.loads(manifest_path.read_text())
    assert is_canonical_id(data["manifest_id"]), (
        f"{manifest_path.name}: manifest_id={data['manifest_id']!r} is not canonical"
    )


@pytest.mark.parametrize("manifest_path", list(_manifest_files()))
def test_fixture_manifest_declares_its_true_hash(manifest_path: Path) -> None:
    """identity.overall_hash is the real JCS-SHA256 of the contract, not a placeholder."""
    data = json.loads(manifest_path.read_text())
    assert data["identity"]["overall_hash"] == hash_manifest(data)


@pytest.mark.parametrize("manifest_path", list(_manifest_files()))
def test_fixture_manifest_validates_clean(manifest_path: Path) -> None:
    """The reference validator reports nothing on its own corpus.

    ``check_schema=True`` runs the bundled JSON Schema (which is what a
    non-Python implementation validates against) and ``check_hash=True`` is the
    hash_mismatch check.
    """
    data = json.loads(manifest_path.read_text())
    result = validate_manifest(data, check_hash=True, check_schema=True)
    assert result.valid, [
        (i.code, i.message) for i in result.issues if i.severity == Severity.ERROR
    ]
    assert result.issues == [], [(i.severity.value, i.code, i.message) for i in result.issues]


@pytest.mark.parametrize("scenario_dir", list(_scenarios()))
def test_expected_diff_ids_track_the_inputs(scenario_dir: Path) -> None:
    """The expectation moves with the inputs — same ids, still canonical."""
    before = json.loads((scenario_dir / "before.json").read_text())
    after = json.loads((scenario_dir / "after.json").read_text())
    expected = json.loads((scenario_dir / "expected-diff.json").read_text())

    assert expected["old_manifest_id"] == before["manifest_id"]
    assert expected["new_manifest_id"] == after["manifest_id"]
    assert is_canonical_id(expected["old_manifest_id"])
    assert is_canonical_id(expected["new_manifest_id"])
