# AgentVersion → A2A Agent Card mapping

[A2A (Agent2Agent)](https://a2a-protocol.org/) is the emerging interoperability standard for how agents
*advertise themselves* to other agents: an **Agent Card** is the public JSON descriptor (name,
capabilities, the skills the agent offers, default I/O modes). It answers **"what can this agent do and
how do I talk to it?"**

AgentVersion answers a different, complementary question A2A does **not**: **"what *is* this agent
version, exactly — and what broke when it changed?"** A diffable, canonically-hashed contract of the
agent's internals plus a breaking-change → data-compatibility decision.

So the relationship is layered, not competing: **AgentVersion is the version / diff / provenance layer
that sits on top of an A2A Agent Card.** `agentversion.manifest_to_agent_card(manifest)` is that seam.

## What maps

| Agent Card field | From the manifest |
|---|---|
| `name` | `agent_name` |
| `version` | `version_label` |
| `description` | `description` |
| `capabilities.{streaming,pushNotifications,stateTransitionHistory}` | `capabilities` block (conservative `false` defaults) |
| `defaultOutputModes` | `contract.output_contract.format` (+ `modalities`) → MIME types |
| `defaultInputModes` | `["text/plain"]` (manifests do not yet model input modes) |
| `skills[]` | `contract.skill_registry.skills` → `{id, name, description, tags}` |
| `provider.organization` | `created_by.organization` (when present) |
| `url` | **caller-supplied** — a deployment endpoint, not part of the internal contract |

## What does NOT map (by design)

The Agent Card is a deliberately **lossy projection** — it advertises a subset of the contract. The full
`model_runtime`, `tool_registry`, `prompt_stack`, `workflow`, `guardrails`, and `output_contract` schema
details stay in the manifest. The card is the public face; the manifest is the source of truth.

## Provenance — the differentiation

The projected card carries an `x-agentversion` extension block:

```json
"x-agentversion": {
  "manifest_id": "amf_…",
  "overall_hash": "sha256:…",
  "spec_version": "1.0.0"
}
```

A2A Agent Cards permit additional fields. This block lets a card consumer resolve **exactly which
versioned, hashed manifest** a card was projected from — pinning identity and enabling diff/compatibility
checks against that specific version. That linkage is precisely what an Agent Card alone cannot provide,
and it is the reason to run AgentVersion alongside A2A rather than instead of it.
