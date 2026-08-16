# AgentVersion

*Part of [DecimalAI](https://decimal.ai). Most users want the Python SDK → [decimal-labs/decimalai-python](https://github.com/decimal-labs/decimalai-python).*

**Your agent changed. Is your saved data still valid?**

[![PyPI](https://img.shields.io/pypi/v/agentversion)](https://pypi.org/project/agentversion/)
[![Downloads](https://static.pepy.tech/badge/agentversion/month)](https://pepy.tech/project/agentversion)
[![CI](https://img.shields.io/github/actions/workflow/status/decimal-labs/agentversion/ci.yml?branch=main)](https://github.com/decimal-labs/agentversion/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/agentversion/)
[![Spec](https://img.shields.io/badge/spec-v1.0-success)](https://pypi.org/project/agentversion/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/decimal-labs/agentversion/blob/main/LICENSE)

When you ship a new version of an agent, everything you collected against the old one — production traces, eval datasets, SFT (supervised fine-tuning) examples — quietly drifts out of date. There's no `package.json` to pin an agent's contract, and no `git diff` to tell you what changed.

`agentversion` is that missing format. Three steps, one per noun:

```
manifest   →   diff   →   compatibility decision
(what an       (what         (what to do with the data
 agent          changed,      you already collected:
 version is)    per surface)   keep / repair / replay / drop)
```

A **surface** is one independently-versioned part of the agent — its prompts, its tools, its model, its graph, its output format — each hashed on its own, so any change can be pinned to exactly one of them. A **diff** classifies each changed surface as breaking or non-breaking; a **compatibility decision** turns that into a per-data verdict.

It's a dependency-light Python package with a CLI — and an open spec any tool can implement.

---

## See it in action

Two production manifests of the same `finance-agent`, `v1` and `v2`. One command:

```console
$ agentversion diff finance-agent-v1.json finance-agent-v2.json --compat
```

```
                                     Manifest Diff
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Surface         ┃ Change Type  ┃ Details                                             ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ environment     │ non_breaking │ deployment_id: None → 'prod-east-1'                 │
│                 │              │ region: None → 'us-east-1'                          │
│                 │              │ infra_image_hash: None →                            │
│                 │              │ 'sha256:img2img2img2img2img2img2img2img2img2img2im… │
│                 │              │ runtime_versions added=app-runtime,python           │
│                 │              │ external_service_pins changed                       │
│                 │              │ resource_limits changed                             │
│ model_runtime   │ breaking     │ provider: 'google' → 'openai'                       │
│                 │              │ runtime_version: 'app-runtime@1.5.0' →              │
│                 │              │ 'app-runtime@1.8.2'                                 │
│                 │              │ envelope changed                                    │
│ output_contract │ breaking     │ format: 'text' → 'json'                             │
│                 │              │ output schema changed                               │
│                 │              │ strict: False → True                                │
│ prompt_stack    │ non_breaking │ system_prompt hash changed                          │
│                 │              │ developer_prompt hash changed                       │
│ subagents       │ breaking     │ subagents added: ['finance_subagent',               │
│                 │              │ 'spreadsheet_subagent']                             │
│ tool_registry   │ breaking     │ search_population removed                            │
│                 │              │ get_population added                                │
│                 │              │ write_spreadsheet_cell added                        │
│                 │              │ get_market_cap modified (non-schema)                │
│ workflow        │ breaking     │ graph topology changed                              │
│                 │              │ routing_policy_version: '2' → '4'                   │
│                 │              │ graph_version: '3' → '6'                            │
│                 │              │ graph_name: 'finance-simple-graph' →                │
│                 │              │ 'finance-router-graph'                              │
└─────────────────┴──────────────┴─────────────────────────────────────────────────────┘

  Breaking: 5  Non-breaking: 2

  Recommendation: replay
  Breaking changes in model_runtime, output_contract, subagents, tool_registry,
  workflow — existing data should be replayed against the new agent version.
```

Between v1 and v2 the team swapped the model (Google → OpenAI), renamed a tool, added two subagents, and switched to strict JSON output. `agentversion` caught all five breaking surfaces and told you the old traces need a replay — not a guess, a classification you can gate CI on.

The recommendation is one of **four verdicts** — what to do with each piece of data you collected against the old version:

| Verdict | What it means | Typical trigger |
|---|---|---|
| `keep`   | Still valid as-is. | Only non-breaking surfaces changed. |
| `repair` | Salvageable with a transform — patch it, don't re-run the agent. | A recoverable output-contract change (the bundled default rules emit `repair` only for output-contract-only breaks). |
| `replay` | Re-run it through the new version for fresh outputs. | A breaking surface (tool, model, workflow) makes old *outputs* untrustworthy but the *inputs* still apply. |
| `drop`   | No longer usable — discard it. | The inputs themselves no longer apply. (`drop` comes from a custom policy, not the default `diff --compat` rules.) |

In the demo above, five breaking surfaces (model swap, tool rename, new subagents, strict-JSON output, new graph) make the old *outputs* stale — but the old *inputs* still apply — so the verdict is `replay`.

### What a manifest looks like

A manifest is plain JSON. The top says *which* version this is; `contract` holds one entry per **surface** — exactly the rows you saw in the diff above:

```jsonc
{
  "agent_name": "finance-agent",
  "version_label": "2026-03-01.prod.1",
  "identity": {
    "overall_hash": "sha256:47301b25...",   // stable id for this whole version
    "hash_algorithm": "jcs-sha256"
  },
  "contract": {
    "prompt_stack":    { "system_prompt": { "version": "8", "hash": "sha256:aaa1..." }, "...": "..." },
    "model_runtime":   { "provider": "google", "model": "gemini-2.0-flash", "...": "..." },
    "tool_registry":   { "registry_version": "5", "tools": [ /* get_market_cap, search_population */ ] },
    "workflow":        { "graph_name": "finance-simple-graph", "graph_version": "3", "...": "..." },
    "subagents":       [],
    "output_contract": { "format": "text", "strict": false, "...": "..." },
    "guardrails":      { "bundle_version": "3", "...": "..." },
    "context_config":  { "retrieval_config_version": "5", "...": "..." }
  }
}
```

Each surface is hashed on its own, so the diff can say *"`tool_registry` changed, `prompt_stack` didn't"* instead of just *"the manifest changed."*

> Try it yourself — both [`examples/manifest/`](https://github.com/decimal-labs/agentversion/tree/main/examples/manifest)
> manifests ship inside the `agentversion` wheel as well as in the repo; the commands below use the
> repo-relative paths, so clone first.

---

## Why an agent needs a version contract

You probably already have observability and a trace store. None of them answer *"what is this agent version, and is my old data still compatible with the new one?"*

| You already have | What it gives you | What it doesn't |
|---|---|---|
| OpenTelemetry and the tracing tools built on it | rich execution traces | a versioned contract for the agent that produced them |
| A2A / ACP agent cards | runtime discovery + I/O types | version identity or data-compatibility |
| OpenAI JSONL / SFT files | a training format | provenance — *which agent version* produced each row |

**Isn't this A2A?** No — and they compose. A2A and ACP (the Agent-to-Agent and Agent Communication protocols) answer *"how does Agent A discover and talk to Agent B?"*. `agentversion` answers *"what changed in this agent, and what does that mean for my data?"*. An A2A Agent Card can carry an `agentversion` manifest hash so you know both at once.

---

## Install

```bash
pip install agentversion
```

Apache-2.0, no config — just needs Python 3.10+.

There are **two version numbers**, deliberately different:

- the **wire spec** is frozen at **v1.0** (stable format + conformance suite — safe to build against);
- this **Python package** is still **pre-1.0**, so its API may still shift.

(The `spec-v1.0` and PyPI badges above show each one.)

## Quickstart

First five minutes: **init → hash → validate → diff → gate in CI**.

**1. Scaffold a manifest** for your agent (interactive):

```bash
agentversion init
```

**2. Get its stable id and check it's valid:**

```bash
agentversion hash manifest.json       # a content hash that ignores key order and
                                      # whitespace, so the same agent always hashes the
                                      # same id (JCS-SHA256 = JSON Canonicalization
                                      # Scheme + SHA-256)
agentversion validate manifest.json   # check it against the spec
```

**3. Diff two versions** — against the bundled examples. The paths are relative, so run this from a
checkout (`--compat` adds the keep/repair/replay/drop recommendation; `--json` for machine output):

```bash
git clone https://github.com/decimal-labs/agentversion && cd agentversion
agentversion diff examples/manifest/finance-agent-v1.json \
                  examples/manifest/finance-agent-v2.json --compat
```

**4. Gate breaking changes in CI** — `--fail-on-breaking` exits non-zero when any surface is breaking:

```yaml
# .github/workflows/agent.yml
- name: Block breaking agent changes
  run: agentversion diff baseline-manifest.json current-manifest.json --fail-on-breaking
```

**Use it from Python** — every API below is covered by the test suite:

```python
import json
from agentversion import AgentManifest, validate_manifest_file, hash_manifest
from agentversion.diff import diff_manifests
from agentversion.compatibility import classify_compatibility

old = json.load(open("examples/manifest/finance-agent-v1.json"))
new = json.load(open("examples/manifest/finance-agent-v2.json"))

# Validate + identify a version
assert validate_manifest_file("examples/manifest/finance-agent-v2.json").valid
m = AgentManifest.model_validate(new)
print(m.agent_name, m.identity.overall_hash)   # finance-agent  sha256:767ebff1...

# Diff, then ask what to do with old data
result = diff_manifests(old, new)
print(result.summary.breaking_surfaces)                       # 5

# Pass no policy and the built-in fallback rules apply. They are deliberately
# non-destructive: the worst they will ever recommend is replay, never drop.
print(classify_compatibility(result).recommended_decision)   # replay
```

---

## What's in the box

A typed reference implementation: Pydantic models, canonical hashing, the diff/compatibility algorithms, and a CLI.

**CLI**

| Command | What it does |
|---|---|
| `agentversion diff A B` | Classify changes by surface (`--json`, `--compat`, `--fail-on-breaking`) |
| `agentversion validate M` | Validate a manifest against the spec |
| `agentversion hash M` | Compute the canonical JCS-SHA256 hash |
| `agentversion init` | Scaffold a new manifest interactively |
| `agentversion upgrade M --to X` | Bump a manifest to a newer spec version |
| `agentversion {decision,replay,dataset} validate` | Validate the other spec objects |

**Library** — top-level `agentversion` exports `AgentManifest`, `validate_manifest` / `validate_manifest_file`, `hash_manifest` / `hash_surface`, and `SPEC_VERSION`. The algorithms live in `agentversion.diff` and `agentversion.compatibility`; the other spec models live in `agentversion.dataset`, `agentversion.replay`, and `agentversion.decision`.

The manifest is organized as a **contract surface** per component — `prompt_stack`, `model_runtime`, `tool_registry`, `skill_registry`, `workflow`, `subagents`, `output_contract`, `guardrails`, `context_config`, `environment` — each independently hashed so the diff is surface-level and precise.

---

## Use it anywhere — no platform required

The protocol is fully useful standalone:

1. **Track versions locally** — `init` to scaffold, `hash` for a stable id, `diff` between any two. No account, fully offline.
2. **Gate CI/CD** — `diff --fail-on-breaking` stops a breaking agent change from reaching production.
3. **Annotate traces** — stamp `identity.overall_hash` onto your OpenTelemetry spans as `agentversion.manifest_hash` for version-scoped filtering. See [`examples/integrations/otel_mapping.md`](https://github.com/decimal-labs/agentversion/blob/main/examples/integrations/otel_mapping.md), bundled in the package.
4. **Classify data compatibility** — `diff --compat` (or `decision generate`) gives a per-episode keep / repair / replay / drop verdict you can act on.

A manifest hash is just a string, so it drops into whatever trace store or eval tool you already run — put `identity.overall_hash` on the spans or dataset rows you keep, and the compatibility decisions sit alongside your eval pipeline as ordinary JSON.

---

## The spec & conformance

`agentversion` is an open spec so any tool, in any language, can produce interoperable manifests and diffs:

- [`spec/manifest.md`](https://github.com/decimal-labs/agentversion/blob/main/spec/manifest.md) — the agent manifest
- [`spec/diff.md`](https://github.com/decimal-labs/agentversion/blob/main/spec/diff.md) — surface diffs, breaking vs non-breaking
- [`spec/compatibility-decision.md`](https://github.com/decimal-labs/agentversion/blob/main/spec/compatibility-decision.md) — keep / repair / replay / drop
- [`spec/replay.md`](https://github.com/decimal-labs/agentversion/blob/main/spec/replay.md) · [`spec/dataset.md`](https://github.com/decimal-labs/agentversion/blob/main/spec/dataset.md) — replay jobs and dataset objects with provenance
- [`spec/reference.md`](https://github.com/decimal-labs/agentversion/blob/main/spec/reference.md) — full schemas and validation rules · [`schemas/`](https://github.com/decimal-labs/agentversion/tree/main/schemas) — JSON Schemas

The full spec and JSON Schemas ship inside the `agentversion` wheel. [`CONFORMANCE.md`](https://github.com/decimal-labs/agentversion/blob/main/CONFORMANCE.md) + [`compatibility-tests/`](https://github.com/decimal-labs/agentversion/tree/main/compatibility-tests) are golden in/out pairs that any implementation must reproduce to claim conformance.

---

## Pairs with skillevaluation

A manifest can carry the eval results that gated its release in `evaluation.gates[]`:

```json
{
  "evaluation": {
    "gates": [
      { "name": "regression-suite", "threshold": 0.95, "actual_score": 0.972,
        "passed": true, "ran_at": "2026-03-05T14:00:00Z" }
    ]
  }
}
```

Those scores come from [`skillevaluation`](https://github.com/decimal-labs/skillevaluation), the sibling open spec: `agentversion` versions the agent runtime itself (what an agent version *is* and what changed), while `skillevaluation` A/B-benchmarks a single skill (whether it actually helps).

The [`decimalai`](https://pypi.org/project/decimalai/) Python SDK builds on `agentversion` to add framework adapters (capture a manifest straight from your LangGraph/CrewAI app), trace capture, and managed replay — but you never need it to use the spec.

---

## From the DecimalAI SDK

If you use the [`decimalai`](https://pypi.org/project/decimalai/) SDK you don't hand-write manifests — it captures one straight from your running agent, and `export_manifest` hands it to the OSS tooling here:

```python
import decimalai
from decimalai.schema.manifest import extract_from_config
from agentversion.diff import diff_manifests
from agentversion.compatibility import classify_compatibility

# Capture a manifest from your agent's config (or a framework adapter)…
snap = extract_from_config(
    agent_name="support-agent",
    prompts={"system": "You are a helpful support assistant."},
    models={"default": {"provider": "openai", "model": "gpt-4o"}},
)
manifest = decimalai.export_manifest(snap)        # → an agentversion manifest dict

# …then this package takes over: diff vs your last prod manifest, gate in CI.
diff = diff_manifests(last_prod_manifest, manifest)
print(classify_compatibility(diff).recommended_decision)
```

This is the seam that makes `agentversion` the **open core** of the paid platform: the manifest the SDK captures *is* the format `agentversion diff` consumes, so you can reproduce the platform's diffs and verdicts entirely outside DecimalAI. A runnable version is in [`examples/integrations/decimalai_bridge.py`](https://github.com/decimal-labs/agentversion/blob/main/examples/integrations/decimalai_bridge.py).

---

## Project

The spec is frozen at v1.0; the package is pre-1.0 (see [Install](#install)). Design decisions are logged in [`adrs/`](https://github.com/decimal-labs/agentversion/tree/main/adrs), releases in [`CHANGELOG.md`](https://github.com/decimal-labs/agentversion/blob/main/CHANGELOG.md). Contributions — especially new conformance cases — are genuinely welcome; see [`CONTRIBUTING.md`](https://github.com/decimal-labs/agentversion/blob/main/CONTRIBUTING.md):

```bash
pip install agentversion
agentversion --help
# run the conformance + unit suite from a clone:
git clone https://github.com/decimal-labs/agentversion && cd agentversion
pip install -e ".[dev]" && pytest
```

Licensed under [Apache 2.0](https://github.com/decimal-labs/agentversion/blob/main/LICENSE).

---

[Docs](https://docs.decimal.ai) · [Registry](https://app.decimal.ai/skills) · [SDK](https://github.com/decimal-labs/decimalai-python) · [skillevaluation](https://github.com/decimal-labs/skillevaluation) · [regression-check](https://github.com/decimal-labs/regression-check)
