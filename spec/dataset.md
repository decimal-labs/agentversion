# Agent Dataset Spec

> Status: Stable v1.0 · Added in v0.1.0

Defined in the AgentVersion. See also [hashing.md](./hashing.md) and [versioning-policy.md](./versioning-policy.md).


This is the canonical schema for trace-derived objects.

## Main objects

* `task`
* `episode`
* `step`
* `dataset_snapshot`

---

## 2.1 Task object

```json
{
  "spec_version": "1.0.0",
  "kind": "task",
  "task_id": "tsk_01JXYZ...",
  "source": {
    "type": "production",
    "system": "langsmith",
    "external_id": "ls_task_123"
  },
  "created_at": "2026-03-10T15:00:00Z",
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "What is Nvidia market cap today?"
      }
    ]
  },
  "attachments": [],
  "metadata": {
    "domain": "finance",
    "priority": "high"
  },
  "tags": ["evergreen", "market-data"]
}
```

> **Multi-turn support:** `input.messages` is an array and supports full multi-turn conversations. Include the complete conversation history (alternating `user`/`assistant` roles) as the task input. Use `metadata.turn_count` and `metadata.is_multi_turn` as recommended conventions for filtering.

---

## 2.2 Episode object

Represents one execution attempt of a task.

```json
{
  "spec_version": "1.0.0",
  "kind": "episode",
  "episode_id": "ep_01JXYZ...",
  "task_id": "tsk_01JXYZ...",
  "source": {
    "type": "production_trace",
    "system": "langsmith",
    "external_trace_id": "trace_abc"
  },
  "manifest_id": "amf_01JXYZ...",
  "status": "success",
  "started_at": "2026-03-10T15:01:00Z",
  "ended_at": "2026-03-10T15:01:05Z",
  "step_ids": ["stp_1", "stp_2", "stp_3"],
  "result": {
    "final_output": {
      "text": "Nvidia's market cap is ..."
    },
    "success_label": true
  },
  "lineage": {
    "parent_episode_id": null,
    "derived_from": "original"
  },
  "observability_refs": {
    "otel_trace_id": "abc123",
    "source_url": "https://..."
  }
}
```

---

## 2.3 Step object

Represents one atomic step.

```json
{
  "spec_version": "1.0.0",
  "kind": "step",
  "step_id": "stp_1",
  "episode_id": "ep_01JXYZ...",
  "index": 1,
  "step_type": "llm_call",
  "started_at": "2026-03-10T15:01:00Z",
  "ended_at": "2026-03-10T15:01:01Z",

  "actor": {
    "type": "agent",
    "name": "finance_subagent"
  },

  "input": {
    "messages": [
      {
        "role": "system",
        "content_ref": "blob://prompt/123"
      },
      {
        "role": "user",
        "content": "What is Nvidia market cap today?"
      }
    ]
  },

  "output": {
    "tool_call": {
      "name": "get_market_cap",
      "arguments": {
        "ticker": "NVDA"
      }
    }
  },

  "schema_refs": {
    "tool_input_schema_hash": "sha256:..."
  },

  "observability_refs": {
    "otel_trace_id": "abc123",
    "otel_span_id": "def456"
  },

  "metadata": {
    "token_usage": {
      "input_tokens": 201,
      "output_tokens": 16
    }
  }
}
```

### Allowed `step_type`

* `llm_call`
* `tool_call`
* `router_decision`
* `subagent_handoff`
* `validator_check`
* `memory_read`
* `memory_write`
* `retrieval`
* `system_event`

---

## 2.4 Dataset snapshot object

Represents a curated frozen dataset.

```json
{
  "spec_version": "1.0.0",
  "kind": "dataset_snapshot",
  "snapshot_id": "dss_01JXYZ...",
  "name": "finance_sft_candidate_2026_03_10",
  "dataset_type": "sft",
  "created_at": "2026-03-10T16:00:00Z",
  "selection_policy": {
    "source_types": ["production", "replay"],
    "required_episode_status": "success",
    "required_policy_compliance": true
  },
  "item_refs": [
    {
      "task_id": "tsk_01",
      "episode_id": "ep_01",
      "step_id": "stp_1"
    },
    {
      "task_id": "tsk_01",
      "episode_id": "ep_01",
      "step_id": "stp_2"
    }
  ],
  "lineage": {
    "source_snapshot_ids": [],
    "built_from_manifest_ids": ["amf_01JXYZ..."]
  }
}
```
