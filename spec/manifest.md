# Agent Manifest Spec (`agentversion.json`)

> Status: Stable v1.0 · Added in v0.1.0

See also [hashing.md](./hashing.md), [diff.md](./diff.md), and [versioning-policy.md](./versioning-policy.md).

## Purpose

Defines the **identity** and **diffable contract surface** of an agent runtime version.

## Design principles

* human-readable JSON/YAML
* stable IDs
* explicit hashes
* narrow and opinionated
* references allowed, but key contract fields should be materialized

---

## Top-level schema

```json
{
  "spec_version": "1.0.0",
  "kind": "agent_manifest",
  "manifest_id": "amf_01JXYZ...",
  "agent_name": "finance-agent",
  "agent_namespace": "acme",
  "version_label": "2026-03-10.prod.4",
  "created_at": "2026-03-10T15:30:00Z",
  "created_by": {
    "type": "user",
    "id": "stanley"
  },
  "parent_manifest_id": "amf_01JXYA...",
  "description": "Adds finance subagent and stricter JSON output",
  "status": "active",
  "tags": ["prod", "finance", "json-output"],
  "capabilities": {
    "streaming": false,
    "multi_turn": true,
    "tool_use": true,
    "structured_output": true
  },

  "identity": {
    "overall_hash": "sha256:abc123...",
    "hash_algorithm": "jcs-sha256",
    "source_commit": "git:8f3b2c1",
    "build_id": "build_1234"
  },

  "contract": {
    "prompt_stack": {
      "system_prompt": {
        "id": "prompt_system_main",
        "version": "12",
        "hash": "sha256:..."
      },
      "developer_prompt": {
        "id": "prompt_dev_main",
        "version": "4",
        "hash": "sha256:..."
      },
      "prompt_assembly_version": "3",
      "scratchpad_format_version": "2",
      "reasoning_policy": "hidden"
    },

    "model_runtime": {
      "provider": "openai",
      "model": "gpt-5.4",
      "model_config_hash": "sha256:...",
      "tool_calling_mode": "structured",
      "runtime_version": "app-runtime@1.8.2",
      "generation_config": {
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 4096,
        "response_format": "json_object"
      }
    },

    "tool_registry": {
      "registry_version": "7",
      "registry_hash": "sha256:...",
      "tools": [
        {
          "name": "get_market_cap",
          "version": "2",
          "hash": "sha256:...",
          "input_schema_hash": "sha256:...",
          "output_schema_hash": "sha256:...",
          "stability": "stable"
        },
        {
          "name": "write_spreadsheet_cell",
          "version": "3",
          "hash": "sha256:...",
          "input_schema_hash": "sha256:...",
          "output_schema_hash": "sha256:...",
          "stability": "stable"
        }
      ]
    },

    "workflow": {
      "graph_name": "finance-router-graph",
      "graph_version": "6",
      "graph_hash": "sha256:...",
      "routing_policy_version": "4"
    },

    "subagents": [
      {
        "name": "finance_subagent",
        "version": "3",
        "hash": "sha256:...",
        "manifest_ref": "amf_finance_subagent_v3",
        "handoff_schema_hash": "sha256:..."
      },
      {
        "name": "spreadsheet_subagent",
        "version": "2",
        "hash": "sha256:...",
        "manifest_ref": "amf_spreadsheet_subagent_v2",
        "handoff_schema_hash": "sha256:..."
      }
    ],

    "output_contract": {
      "version": "3",
      "schema_hash": "sha256:...",
      "format": "json",
      "strict": true
    },

    "guardrails": {
      "bundle_version": "5",
      "bundle_hash": "sha256:..."
    },

    "context_config": {
      "retrieval_config_version": "8",
      "retrieval_config_hash": "sha256:...",
      "memory_policy_version": "2",
      "context_packing_version": "3"
    },

    "environment": {
      "deployment_id": "prod-east-1",
      "region": "us-east-1",
      "infra_image_hash": "sha256:...",
      "runtime_versions": { "python": "3.12.5", "app-runtime": "1.8.2" },
      "external_service_pins": { "openai": "v1@2024-10-01" }
    }
  },

  "extensions": {
    "otel": {
      "service_name": "finance-agent-service",
      "deployment_environment": "prod"
    }
  }
}
```

> **Current surface set.** This example leads with the legacy top-level `status` enum
> for back-compat. New manifests should prefer the richer `lifecycle` block (see
> [lifecycle.md](./lifecycle.md)) and may carry an `evaluation` block (see
> [evaluation.md](./evaluation.md)). The `contract` also supports `skill_registry`
> and `behavioral_policy` surfaces (omitted above for brevity) — see
> [diff.md](./diff.md) for the full diffable surface set.

---

## Required fields

Minimum required:

* `spec_version`
* `kind`
* `manifest_id`
* `agent_name`
* `version_label`
* `created_at`
* `identity.overall_hash`
* `contract.prompt_stack`
* `contract.model_runtime`
* `contract.tool_registry`
* `contract.workflow`
* `contract.output_contract`

---

## Key idea: contract surfaces

The manifest should support diffing by **surface**:

* prompt surface (`prompt_stack`)
* model/runtime surface (`model_runtime`)
* tool surface (`tool_registry`)
* skill surface (`skill_registry`)
* workflow surface (`workflow`)
* subagent surface (`subagents`)
* output surface (`output_contract`)
* guardrail surface (`guardrails`)
* context surface (`context_config`)
* environment surface (`environment`)
* behavioral-policy surface (`behavioral_policy`)

(`AgentContract` is `extra="allow"`, so producers may add further surfaces; the hasher hashes every contract key and the diff engine reports them. The example above shows only the core required surfaces.)

That lets you say:

* tool surface changed
* output surface changed
* workflow surface changed

instead of just "manifest changed."
