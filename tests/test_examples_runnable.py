"""Smoke tests: every bundled example script actually runs.

The langgraph example previously bit-rotted (placeholder hashes, an undefined
symbol in its usage block) because nothing ever executed it. These tests run each
example end-to-end so a future break is caught in CI.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# (script, expected_exit). walkthrough.py mirrors the CI gate: it exits non-zero
# when the diff has breaking changes (the finance v1→v2 pair does).
_EXAMPLES = [
    ("examples/integrations/decimalai_bridge.py", 0),
    ("examples/integrations/langgraph_example.py", 0),
    ("examples/scenarios/walkthrough.py", 1),
]


@pytest.mark.parametrize("script,expected_exit", _EXAMPLES)
def test_example_runs(script: str, expected_exit: int) -> None:
    result = subprocess.run(
        [sys.executable, str(_ROOT / script)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(_ROOT),
    )
    assert result.returncode == expected_exit, (
        f"{script} exited {result.returncode}, expected {expected_exit}\n{result.stderr}"
    )
    assert result.stdout.strip(), f"{script} produced no output"
