# Drift Scenario: Tool Rename + Output Format Change

This walkthrough demonstrates the full AgentVersion workflow when an agent
undergoes a breaking change between two versions.

> **Runnable version:** [`walkthrough.py`](./walkthrough.py) executes every step
> below on the bundled manifests and prints the real output — run it with
> `python examples/scenarios/walkthrough.py` (it's covered by the test suite, so
> it can't go stale).

## Scenario

Your finance agent v1 → v2:
- **Model swapped**: Google → OpenAI
- **Tool renamed**: `search_population` → `get_population` (+ a destructive tool added)
- **Output format**: plain text → strict JSON
- **New subagents** added, **new graph** topology

Both versions have manifests:
- [`finance-agent-v1.json`](../manifest/finance-agent-v1.json)
- [`finance-agent-v2.json`](../manifest/finance-agent-v2.json)

## Step 1 — Diff the manifests

```bash
agentversion diff examples/manifest/finance-agent-v1.json \
                  examples/manifest/finance-agent-v2.json
```

This classifies each changed surface as `breaking` / `non_breaking` with a
`minor` / `moderate` / `major` severity. For this pair it reports **5 breaking,
2 non-breaking** surfaces (model_runtime, output_contract, subagents,
tool_registry, workflow are breaking; environment and prompt_stack are not). See
the README's "See it in action" for the rendered table.

## Step 2 — Classify compatibility

```bash
agentversion diff examples/manifest/finance-agent-v1.json \
                  examples/manifest/finance-agent-v2.json --compat
```

**Replay recommended** — tools were removed/renamed and the model changed, so old
traces that used `search_population` (or were graded against the old model/output
contract) are no longer trustworthy. The inputs still apply, so `replay` rather
than `drop`.

## Step 3 — Generate a per-episode decision

```bash
agentversion decision generate \
  examples/manifest/finance-agent-v1.json \
  examples/manifest/finance-agent-v2.json \
  --subject-id ep_old_123
```

Outputs a `compatibility_decision` for that episode: `decision: "replay"` plus the
`reason_codes` that led there (e.g. `tool_missing`, `model_runtime_changed`,
`output_contract_changed`, `workflow_surface_changed`, …). `walkthrough.py` prints
the full object.

## Step 4 — Gate it in CI/CD

```yaml
- name: Check for breaking agent changes
  run: |
    agentversion diff main-manifest.json current.json --fail-on-breaking
```

`--fail-on-breaking` exits non-zero when any surface is breaking, blocking the
deploy until the impact is assessed.
