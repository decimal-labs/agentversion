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
