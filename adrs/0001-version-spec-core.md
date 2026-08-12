---
title: "ADR 0001: AgentVersion Core Design"
status: Accepted
date: 2026-03-10
---

# ADR 0001: AgentVersion Core Design

## Context

AI agents accumulate data over time — production traces, synthetic tasks,
evaluation results. When the agent changes (prompts update, tools rename,
models swap), that data may become invalid. There is no standard way to
detect this drift or assess its impact.

## Decision

We defined the AgentVersion with six related specs:

1. **Agent Manifest** — Identity and diffable contract surface of an agent version
2. **Dataset Spec** — Canonical schema for tasks, episodes, steps, snapshots
3. **Rescue Decision** — Per-episode classification (keep / repair / replay / drop)
4. **Replay Job** — Replay job input, constraints, and results
5. **Diff Spec** — Surface-level diff format between manifests
6. **Rescue Batch** — Batch classification for platform-scale decisions

### Key Design Decisions

- **Contract-only hashing**: Only the `contract` block contributes to the
  identity hash. Metadata changes don't affect identity.
- **Surface-level diffing**: Changes are classified per-surface (tools, prompts,
  model, workflow, etc.) rather than as a monolithic diff.
- **JCS-SHA256**: Uses RFC 8785 JSON Canonicalization Scheme for deterministic
  hashing across implementations.
- **Extensible**: The `extensions` field allows platform-specific metadata
  without polluting the core spec.

### Compatibility Classification

The spec defines a taxonomy for assessing impact:

| Decision | When to use |
|---|---|
| **keep** | No breaking changes; data remains valid |
| **repair** | Data can be migrated (e.g., output schema change) |
| **replay** | Data must be re-generated against the new agent |
| **drop** | Data cannot be recovered and should be removed |

## Consequences

- A reference implementation in Python is provided:
  - Pydantic models for all spec objects
  - JCS-SHA256 hasher
  - Semantic validator
  - Surface-level diff engine
  - Compatibility classifier
  - CLI tool (`agentversion`)
- The spec is in **alpha** status (v0.1). Breaking changes may occur until v1.0.

## References

- [spec/reference.md](../spec/reference.md) — Full specification
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) — JSON Canonicalization Scheme
- [Semantic Versioning 2.0.0](https://semver.org/)
