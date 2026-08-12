# Replay Job Spec

> Status: Stable v1.0 · Added in v0.1.0

Defined in the AgentVersion. See also [hashing.md](./hashing.md) and [versioning-policy.md](./versioning-policy.md).


This needs to be very explicit.

## Replay job

```json
{
  "spec_version": "1.0.0",
  "kind": "replay_job",
  "replay_job_id": "rpj_01JXYZ...",
  "task_id": "tsk_01JXYZ...",
  "source_episode_id": "ep_old_123",
  "target_manifest_id": "amf_new_456",

  "mode": "customer_runtime",
  "priority": "normal",

  "replay_input": {
    "messages": [
      {
        "role": "user",
        "content": "What is Nvidia market cap today?"
      }
    ],
    "conversation_history": [],
    "attachments": [],
    "context_refs": []
  },

  "constraints": {
    "timeout_seconds": 120,
    "max_cost_usd": 2.0,
    "allow_network": true
  },

  "requested_outputs": {
    "include_full_trace": true,
    "include_step_artifacts": true,
    "include_final_output": true
  },

  "lineage": {
    "requested_from_episode_id": "ep_old_123"
  },

  "created_at": "2026-03-10T16:10:00Z"
}
```

---

## Replay result

```json
{
  "spec_version": "1.0.0",
  "kind": "replay_result",
  "replay_job_id": "rpj_01JXYZ...",
  "status": "completed",
  "target_manifest_id": "amf_new_456",
  "replayed_episode_id": "ep_new_789",
  "replayability": "fully_replayable",
  "runtime_metadata": {
    "executor_type": "langgraph_worker",
    "executor_version": "0.1.2"
  },
  "comparison_summary": {
    "final_output_changed": true,
    "tool_path_changed": true,
    "output_contract_valid": true
  },
  "completed_at": "2026-03-10T16:12:00Z"
}
```

## Allowed replay result status

* `queued`
* `running`
* `completed`
* `failed`
* `cancelled`

## Allowed replayability

* `fully_replayable`
* `partially_replayable`
* `not_replayable`
