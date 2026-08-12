# OTEL GenAI Attribute Mapping

This document provides a canonical mapping between AgentVersion manifest fields and
[OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).

## Agent Identity

| AgentVersion field | OTEL attribute | Notes |
|---|---|---|
| `agent_name` | `gen_ai.agent.name` | |
| `agent_namespace` | `gen_ai.agent.description` | Mapped to namespace |
| `manifest_id` | `agentversion.manifest_id` | Custom attribute |
| `version_label` | `agentversion.version_label` | Custom attribute |
| `identity.overall_hash` | `agentversion.manifest_hash` | Custom attribute |
| `spec_version` | `agentversion.spec_version` | Custom attribute |

## Model Runtime

| AgentVersion field | OTEL attribute | Notes |
|---|---|---|
| `contract.model_runtime.provider` | `gen_ai.system` | e.g. `openai`, `google` |
| `contract.model_runtime.model` | `gen_ai.request.model` | |
| `contract.model_runtime.generation_config.temperature` | `gen_ai.request.temperature` | |
| `contract.model_runtime.generation_config.top_p` | `gen_ai.request.top_p` | |
| `contract.model_runtime.generation_config.max_tokens` | `gen_ai.request.max_tokens` | |

## Tool Usage

| AgentVersion field | OTEL attribute | Notes |
|---|---|---|
| `contract.tool_registry.tools[].name` | `gen_ai.tool.name` | Per-tool call span |
| `contract.tool_registry.tools[].description` | `gen_ai.tool.description` | Per-tool call span |

## Observability Refs (Episode / Step)

| AgentVersion field | OTEL attribute | Notes |
|---|---|---|
| `observability_refs.otel_trace_id` | `trace_id` | Direct trace correlation |
| `observability_refs.otel_span_id` | `span_id` | Direct span correlation |

## Custom Namespace

All AgentVersion-specific attributes use the `agentversion.` prefix:

```
agentversion.manifest_id
agentversion.manifest_hash
agentversion.version_label
agentversion.spec_version
agentversion.surface.<name>.hash     # per-surface hash
```

## Integration Pattern

When exporting traces via OTEL, the SDK should attach these attributes
to the root span of each trace:

```python
from opentelemetry import trace

span = trace.get_current_span()
span.set_attribute("gen_ai.agent.name", manifest.agent_name)
span.set_attribute("gen_ai.system", manifest.contract.model_runtime.provider)
span.set_attribute("gen_ai.request.model", manifest.contract.model_runtime.model)
span.set_attribute("agentversion.manifest_hash", manifest.identity.overall_hash)
```
