"""Bridge: a manifest from the DecimalAI SDK → agentversion diff / compat.

The DecimalAI SDK (``pip install decimalai``) captures a manifest straight from your
running agent (LangGraph / CrewAI / explicit config). ``decimalai.export_manifest``
emits an *agentversion* manifest dict — so the OSS tooling in this package takes over
for the diff and the keep / repair / replay / drop verdict, and you can gate it in CI.

    DecimalAI SDK                          agentversion (this package)
    extract_from_config(...)  ──►  export_manifest(snap)  ──►  diff_manifests(old, new)
                                   (an agentversion dict)       classify_compatibility(diff)

This is the seam that makes agentversion the *open core* of the paid platform: the
manifest the SDK captures is the very format ``agentversion diff`` consumes — you can
reproduce the platform's diffs and verdicts entirely outside DecimalAI.

Run it::

    pip install decimalai agentversion
    python decimalai_bridge.py

Without the SDK installed it still runs, falling back to the two bundled example
manifests, so the agentversion half is always demonstrable.
"""
from __future__ import annotations

import json
from pathlib import Path

from agentversion.compatibility import classify_compatibility
from agentversion.diff import diff_manifests

_EXAMPLES = Path(__file__).resolve().parent.parent / "manifest"


def from_decimalai_sdk() -> tuple[dict, dict] | None:
    """Capture v1 + v2 of a tiny support agent via the DecimalAI SDK.

    Each manifest is exported to the agentversion contract shape. Returns ``None``
    if the SDK isn't installed, so ``main`` can fall back to the bundled examples.
    """
    try:
        import decimalai
        from decimalai.schema.manifest import extract_from_config
    except ImportError:
        return None

    # v1 of a support agent.
    v1 = decimalai.export_manifest(extract_from_config(
        agent_name="support-agent",
        prompts={"system": "You are a helpful support assistant."},
        models={"default": {"provider": "openai", "model": "gpt-4o"}},
        tools=[{"name": "lookup_order", "description": "Look up an order by id."}],
        version_label="v1",
    ))
    # v2: the team swapped the model provider and added a destructive tool — a
    # breaking change that makes traces collected against v1 untrustworthy.
    v2 = decimalai.export_manifest(extract_from_config(
        agent_name="support-agent",
        prompts={"system": "You are a helpful support assistant."},
        models={"default": {"provider": "anthropic", "model": "claude-haiku-4-5"}},
        tools=[
            {"name": "lookup_order", "description": "Look up an order by id."},
            {"name": "issue_refund", "description": "Issue a refund for an order."},
        ],
        version_label="v2",
    ))
    return v1, v2


def from_bundled_examples() -> tuple[dict, dict]:
    """Fallback: the two example manifests bundled with agentversion."""
    v1 = json.loads((_EXAMPLES / "finance-agent-v1.json").read_text())
    v2 = json.loads((_EXAMPLES / "finance-agent-v2.json").read_text())
    return v1, v2


def main() -> None:
    pair = from_decimalai_sdk()
    if pair is None:
        print("decimalai SDK not installed — using the bundled example manifests.")
        print("(`pip install decimalai` to capture a manifest from your own agent.)\n")
        old, new = from_bundled_examples()
    else:
        print("Captured v1 + v2 via the DecimalAI SDK, exported to agentversion.\n")
        old, new = pair

    diff = diff_manifests(old, new)
    report = classify_compatibility(diff)

    print(
        f"{diff.summary.breaking_surfaces} breaking / "
        f"{diff.summary.non_breaking_surfaces} non-breaking surface(s):"
    )
    for change in diff.changed_surfaces:
        print(f"  - {change.surface}: {change.change_type} ({change.severity})")
    print(f"\nVerdict for data collected against the old version: {report.recommended_decision}")


if __name__ == "__main__":
    main()
