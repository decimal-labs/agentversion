# Diff Spec

> Status: Stable v1.0 · Added in v0.1.0

Defined in the AgentVersion. See also [hashing.md](./hashing.md) and [versioning-policy.md](./versioning-policy.md).


Standard diff result format. Each changed surface carries both a `change_type`
(`breaking` / `non_breaking`) and a `severity` (`minor` / `moderate` / `major`);
the summary rolls these up with a `max_severity`. For example, a tool **removal**
is `breaking` + `major`, while a tool **add** is `non_breaking` + `minor`.

```json
{
  "spec_version": "1.0.0",
  "kind": "manifest_diff",
  "old_manifest_id": "amf_old",
  "new_manifest_id": "amf_new",
  "changed_surfaces": [
    {
      "surface": "tool_registry",
      "change_type": "breaking",
      "severity": "major",
      "details": ["search_population removed", "get_population added"]
    },
    {
      "surface": "workflow",
      "change_type": "breaking",
      "severity": "major",
      "details": ["router node added", "finance subagent introduced"]
    },
    {
      "surface": "output_contract",
      "change_type": "breaking",
      "severity": "minor",
      "details": ["format: 'text' → 'json'"]
    }
  ],
  "summary": {
    "breaking_surfaces": 3,
    "non_breaking_surfaces": 0,
    "max_severity": "major"
  }
}
```

## Suggested `surface`

* `prompt_stack`
* `model_runtime`
* `tool_registry`
* `skill_registry`
* `workflow`
* `subagents`
* `output_contract`
* `guardrails`
* `context_config`
* `environment`
* `behavioral_policy`
