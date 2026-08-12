# Reproducible Replay

> Status: Stable v1.0 · Added in v0.8.0

How to make a replay produce bit-identical output to the original trace. The spec adds four primitives that together make most agents replayable:

| Field / surface | Item | What it pins |
|---|---|---|
| `ReplayInput.determinism.random_seed` | §3f | Sampler randomness (temperature > 0 outputs converge). |
| `ReplayInput.determinism.clock_freeze_at` | §3f | The agent's `now()`. Critical for time-sensitive tools. |
| `ReplayInput.determinism.tool_response_pinning_ref` | §3f | A URI to recorded tool responses, returned instead of live calls. |
| `ToolDescriptor.input_schema_inline` / `output_schema_inline` | §3g | The tool's schemas, embedded so offline replay doesn't need a registry. |

## DeterminismHints

```json
"replay_input": {
  "messages": [...],
  "determinism": {
    "random_seed": 12345,
    "clock_freeze_at": "2026-03-10T15:00:00Z",
    "tool_response_pinning_ref": "agentversion:hash:sha256:abcdef…"
  }
}
```

All three fields are optional and independent. Use whichever you need.

### `random_seed`

Integer seed passed to the sampler. The replay runner is responsible for plumbing it into the model client (e.g. OpenAI's `seed` parameter, vLLM's `seed`, etc.). If your model provider doesn't honor seeds, this field has no effect — but should still be recorded so the discrepancy is auditable.

### `clock_freeze_at`

ISO 8601 datetime. The agent's notion of "now" during replay is exactly this value. Implementations typically expose this via a `Clock` interface the agent's tools consume.

Common cases this catches:
- Market data tools that say "give me the price right now"
- Date-aware prompts ("today is X, plan for next week")
- Cache-key generation that includes `now()`

### `tool_response_pinning_ref`

A URI (see [`refs.md`](./refs.md)) pointing at a JSONL file of recorded tool responses. Format:

```jsonl
{"step_id": "stp_01HZK…", "tool": "get_market_cap", "input_hash": "sha256:…", "output": {...}}
{"step_id": "stp_01HZL…", "tool": "search_population", "input_hash": "sha256:…", "output": {...}}
```

The replay runner returns these recorded outputs instead of calling tools live. Falls back to live invocation if no record matches.

Most useful URI scheme here is `agentversion:hash:` — content-addressed pinning gives you tamper detection for free.

## Tool schema embedding (§3g)

Tools normally identify their schemas by hash:

```json
"input_schema_hash": "sha256:f1a1…"
```

For fully offline replay (e.g. archived agents 5 years later), embed the schema:

```json
"input_schema_hash":   "sha256:f1a1…",
"input_schema_inline": {
  "type": "object",
  "required": ["ticker"],
  "properties": { "ticker": { "type": "string", "pattern": "^[A-Z]{1,5}$" } }
}
```

The validator enforces hash equivalence: `JCS-SHA256(input_schema_inline) == input_schema_hash`. Inline is an *equivalent* representation, not a divergent one — adding it doesn't change the manifest's `overall_hash` (the hash already factored the schema in).

Validator code: `schema_hash_mismatch` (ERROR).

## Why these four together

| Without | With |
|---|---|
| Trace recorded 6 months ago: replay returns mostly different outputs because (a) the model gave a different sample, (b) the agent asked "what's today?" and got today's date, (c) the market data tool returned current prices. Result: `replayability: "partially_replayable"`, useless for regression eval. | Replay returns identical outputs. The diff against the original trace surfaces only changes that come from the new manifest itself, not from a moving world. |
| Tool registry isn't accessible (org dissolved, moved, etc.). Replay can't validate tool calls. | Embedded schemas let the replay runner verify tool I/O independently. |

These four are the minimum to claim "reproducible replay" — production-grade agent eval pipelines typically want all four.

## What's still not deterministic

The spec doesn't (yet) pin:

- **External service responses** other than tool calls (e.g. HTTP fetches inside a prompt template). Use `environment.external_service_pins` (§3a) to document expected versions; full request/response pinning is left to the replay runner.
- **Concurrent tool ordering**. If the agent fires two tool calls in parallel, the order they return in may affect downstream behavior. Out of scope.
- **Floating-point determinism across hardware** (CPU vs GPU, vendor-specific BLAS).
