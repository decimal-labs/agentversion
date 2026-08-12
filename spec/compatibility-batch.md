# Compatibility Batch Spec

> Status: Stable v1.0 · Added in v0.1.0

Defined in the AgentVersion. See also [hashing.md](./hashing.md) and [versioning-policy.md](./versioning-policy.md).


For platform-scale classification where thousands of episodes need compatibility decisions at once.

## Compatibility batch object

```json
{
  "spec_version": "1.0.0",
  "kind": "compatibility_batch",
  "batch_id": "cbt_01JXYZ...",
  "old_manifest_id": "amf_old",
  "target_manifest_id": "amf_new",
  "diff_ref": "diff_01JXYZ...",
  "created_at": "2026-03-10T16:05:00Z",

  "summary": {
    "total_episodes": 10000,
    "keep": 7200,
    "repair": 800,
    "replay": 1500,
    "drop": 500
  },

  "classification_rules": [
    {
      "rule_id": "rule_01",
      "condition": "tool_surface_unchanged AND prompt_surface_unchanged",
      "decision": "keep",
      "matched_count": 7200
    },
    {
      "rule_id": "rule_02",
      "condition": "tool_missing:search_population",
      "decision": "replay",
      "reason_codes": ["tool_missing"],
      "matched_count": 1500
    },
    {
      "rule_id": "rule_03",
      "condition": "output_contract_changed AND episode_uses_json_output",
      "decision": "repair",
      "reason_codes": ["output_contract_changed"],
      "repair_strategy": "schema_migration",
      "matched_count": 800
    },
    {
      "rule_id": "rule_04",
      "condition": "environment_unreplayable",
      "decision": "drop",
      "reason_codes": ["environment_unreplayable", "missing_artifacts"],
      "matched_count": 500
    }
  ],

  "episode_decisions_ref": "compatibility-batch-01JXYZ-decisions.jsonl"
}
```

## Design rationale

* **`classification_rules`** — aggregated logic: "why did we classify this way?" — this is what a reviewing UI surfaces
* **`condition`** — a descriptive, controlled-vocabulary record of *which* rule grouped these episodes (e.g. `tool_surface_unchanged AND prompt_surface_unchanged`). It is validated for well-formedness, but the spec defines no evaluator: classification is performed by the implementation, and the batch only records the result. These condition tokens are deliberately distinct from `reason_codes` — tokens describe the diff (inputs), reason codes explain the decision (outputs)
* **`summary`** — headline numbers without processing thousands of decisions
* **`episode_decisions_ref`** — pointer to a JSONL file with individual per-episode `compatibility_decision` objects, for cases where you need to look up a specific episode
* Individual `compatibility_decision` objects still work standalone — the batch is a collection wrapper, not a replacement

## Pydantic models

```python
class ClassificationRule(BaseModel):
    rule_id: str
    condition: str
    decision: Literal["keep", "repair", "replay", "drop"]
    reason_codes: List[str] = Field(default_factory=list)
    repair_strategy: Optional[str] = None
    matched_count: int


class CompatibilityBatchSummary(BaseModel):
    total_episodes: int
    keep: int
    repair: int
    replay: int
    drop: int


class CompatibilityBatch(BaseModel):
    spec_version: str = "1.0.0"
    kind: Literal["compatibility_batch"] = "compatibility_batch"
    batch_id: str
    old_manifest_id: str
    target_manifest_id: str
    diff_ref: Optional[str] = None
    created_at: datetime
    summary: CompatibilityBatchSummary
    classification_rules: List[ClassificationRule]
    episode_decisions_ref: Optional[str] = None
```
