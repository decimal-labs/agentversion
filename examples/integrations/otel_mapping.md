# OpenTelemetry ↔ AgentVersion Mapping

This document shows how AgentVersion fields map to OpenTelemetry (OTel)
semantic conventions, enabling integration between the two.

> The canonical attribute-key mapping lives in
> [`spec/otel-mapping.md`](../../spec/otel-mapping.md). This file is a worked
> integration example and follows the same `agentversion.*` custom keys.

## Mapping Table

| AgentVersion Field | OTel Semantic Convention | OTel Attribute |
|---|---|---|
| `agent_name` | Service name | `service.name` |
| `version_label` | Service version | `service.version` |
| `agent_namespace` | Service namespace | `service.namespace` |
| `identity.overall_hash` | Custom attribute | `agentversion.manifest_hash` |
| `identity.source_commit` | Source revision | `vcs.revision` |
| `identity.build_id` | Build ID | `service.instance.id` |
| `contract.model_runtime.provider` | LLM provider | `gen_ai.system` |
| `contract.model_runtime.model` | LLM model | `gen_ai.request.model` |
| `contract.model_runtime.generation_config.temperature` | Temperature | `gen_ai.request.temperature` |
| `contract.model_runtime.generation_config.max_tokens` | Max tokens | `gen_ai.request.max_tokens` |
| `contract.model_runtime.generation_config.top_p` | Top-p | `gen_ai.request.top_p` |

## Episode → Trace Mapping

| AgentVersion | OpenTelemetry |
|---|---|
| `episode.episode_id` | `trace_id` (via `observability_refs.otel_trace_id`) |
| `step.step_id` | `span_id` (via `observability_refs.otel_span_id`) |
| `step.step_type` | `span.name` or `span.kind` |
| `step.started_at` | Span start time |
| `step.ended_at` | Span end time |
| `step.metadata.token_usage` | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` |

## Using the `extensions.otel` Block

The manifest's `extensions` field can carry OTel-specific deployment metadata:

```json
{
  "extensions": {
    "otel": {
      "service_name": "finance-agent-service",
      "deployment_environment": "prod",
      "resource_attributes": {
        "cloud.provider": "gcp",
        "cloud.region": "us-central1"
      }
    }
  }
}
```

## Injecting Manifest Identity into Spans

```python
from opentelemetry import trace

def set_manifest_context(manifest: dict):
    """Inject manifest identity into the current OTel span."""
    span = trace.get_current_span()
    span.set_attribute("agentversion.manifest_id", manifest["manifest_id"])
    span.set_attribute("agentversion.manifest_hash", manifest["identity"]["overall_hash"])
    span.set_attribute("agentversion.version_label", manifest["version_label"])
    span.set_attribute("agentversion.spec_version", manifest["spec_version"])
    span.set_attribute("gen_ai.agent.name", manifest["agent_name"])
```

This lets you query traces by manifest version in any OTel-compatible backend
(Jaeger, Grafana Tempo, Google Cloud Trace, etc.).
