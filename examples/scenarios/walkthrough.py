"""Runnable walkthrough: detect drift between finance-agent v1 → v2.

The companion to ``tool-rename-drift.md``, but executable and test-covered (so it
can't bit-rot). It runs the full AgentVersion flow on the two bundled manifests:

    diff  →  compatibility verdict  →  per-episode decision  →  CI gate

Run it::

    python examples/scenarios/walkthrough.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentversion.compatibility import classify_compatibility
from agentversion.decision import CompatibilityDecision, DecisionSubject
from agentversion.diff import diff_manifests
from agentversion.ids import mint_id

_MANIFESTS = Path(__file__).resolve().parent.parent / "manifest"


def run() -> CompatibilityDecision:
    old = json.loads((_MANIFESTS / "finance-agent-v1.json").read_text())
    new = json.loads((_MANIFESTS / "finance-agent-v2.json").read_text())

    # Step 1 — diff the two versions, surface by surface.
    diff = diff_manifests(old, new)
    print("Step 1 — diff")
    for change in diff.changed_surfaces:
        print(f"  {change.surface:<16} {change.change_type:<13} {change.severity}")
    print(f"  → {diff.summary.breaking_surfaces} breaking, "
          f"{diff.summary.non_breaking_surfaces} non-breaking\n")

    # Step 2 — turn the diff into a verdict for the data collected against v1.
    report = classify_compatibility(diff)
    print("Step 2 — compatibility verdict")
    print(f"  recommended decision: {report.recommended_decision}")
    print(f"  reason codes: {', '.join(report.reason_codes)}\n")

    # Step 3 — a per-episode decision (mirrors `agentversion decision generate`).
    decision = CompatibilityDecision(
        decision_id=mint_id("compatibility_decision"),
        subject=DecisionSubject(type="episode", id="ep_old_123"),
        old_manifest_id=diff.old_manifest_id,
        target_manifest_id=diff.new_manifest_id,
        decision=report.recommended_decision,
        reason_codes=report.reason_codes,
        created_at=datetime(2026, 3, 5, 14, 0, tzinfo=timezone.utc),
    )
    print("Step 3 — decision for episode ep_old_123")
    print(json.dumps(json.loads(decision.model_dump_json()), indent=2))

    # Step 4 — in CI, `agentversion diff old new --fail-on-breaking` exits non-zero
    # on any breaking surface, blocking the deploy. Mirror that exit code here.
    print(f"\nStep 4 — CI gate would exit {1 if diff.summary.breaking_surfaces else 0} "
          f"(--fail-on-breaking)")
    return decision


if __name__ == "__main__":
    decision = run()
    # Non-zero exit when there are breaking changes, like the CI gate.
    sys.exit(1 if decision.decision != "keep" else 0)
