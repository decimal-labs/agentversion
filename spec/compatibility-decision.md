# Compatibility Decision Spec

> Status: Stable v1.0 · Added in v0.1.0

Defined in the AgentVersion. See also [hashing.md](./hashing.md) and [versioning-policy.md](./versioning-policy.md).


This is one of the most important open pieces.

```json
{
  "spec_version": "1.0.0",
  "kind": "compatibility_decision",
  "decision_id": "cdc_01JXYZ...",
  "subject": {
    "type": "episode",
    "id": "ep_01JXYZ..."
  },
  "old_manifest_id": "amf_old",
  "target_manifest_id": "amf_new",

  "decision": "replay",
  "reason_codes": [
    "tool_schema_incompatible",
    "workflow_surface_changed"
  ],

  "details": {
    "summary": "Old tool call no longer validates; workflow now routes via finance subagent",
    "confidence": 0.93
  },

  "repair_plan": null,

  "replay_plan": {
    "replayability": "fully_replayable",
    "required_context": ["messages", "attachments"]
  },

  "created_at": "2026-03-10T16:05:00Z"
}
```

## Allowed `decision`

* `keep`
* `repair`
* `replay`
* `drop`

## Suggested `reason_codes`

* `tool_missing`
* `tool_schema_incompatible`
* `tool_semantics_changed`
* `prompt_policy_changed`
* `prompt_format_changed`
* `model_runtime_changed`
* `workflow_surface_changed`
* `subagent_interface_changed`
* `output_contract_changed`
* `guardrail_policy_changed`
* `behavioral_policy_changed`
* `context_config_changed`
* `environment_unreplayable`
* `missing_artifacts`
* `insufficient_confidence`
