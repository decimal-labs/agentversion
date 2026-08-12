"""Tests for compatibility decision and replay models."""

import json
from datetime import datetime, timezone

import pytest

from agentversion.decision import (
    ClassificationRule,
    CompatibilityBatch,
    CompatibilityBatchSummary,
    CompatibilityDecision,
    DecisionDetails,
    DecisionSubject,
    RepairPlan,
    ReplayPlan,
)
from agentversion.replay import (
    Message,
    ReplayInput,
    ReplayJob,
    ReplayResult,
)


class TestCompatibilityDecision:
    def test_parse_keep(self):
        d = CompatibilityDecision(
            decision_id="rdc_001",
            subject=DecisionSubject(type="episode", id="ep_001"),
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            decision="keep",
            reason_codes=[],
            created_at=datetime.now(timezone.utc),
        )
        assert d.decision == "keep"
        assert d.kind == "compatibility_decision"

    def test_parse_replay_with_plan(self):
        d = CompatibilityDecision(
            decision_id="rdc_002",
            subject=DecisionSubject(type="episode", id="ep_002"),
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            decision="replay",
            reason_codes=["tool_missing", "workflow_surface_changed"],
            details=DecisionDetails(summary="Tool removed", confidence=0.93),
            replay_plan=ReplayPlan(
                replayability="fully_replayable",
                required_context=["messages", "attachments"],
            ),
            created_at=datetime.now(timezone.utc),
        )
        assert d.decision == "replay"
        assert d.replay_plan.replayability == "fully_replayable"
        assert d.details.confidence == 0.93

    def test_parse_repair_with_plan(self):
        d = CompatibilityDecision(
            decision_id="rdc_003",
            subject=DecisionSubject(type="episode", id="ep_003"),
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            decision="repair",
            reason_codes=["output_contract_changed"],
            repair_plan=RepairPlan(strategy="schema_migration"),
            created_at=datetime.now(timezone.utc),
        )
        assert d.repair_plan.strategy == "schema_migration"

    def test_roundtrip(self):
        d = CompatibilityDecision(
            decision_id="rdc_004",
            subject=DecisionSubject(type="episode", id="ep_004"),
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            decision="drop",
            reason_codes=["environment_unreplayable"],
            created_at=datetime.now(timezone.utc),
        )
        output = json.loads(d.model_dump_json())
        d2 = CompatibilityDecision.model_validate(output)
        assert d2.decision == "drop"

    def test_validates_against_schema(self):
        import jsonschema

        d = CompatibilityDecision(
            decision_id="rdc_005",
            subject=DecisionSubject(type="episode", id="ep_005"),
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            decision="replay",
            reason_codes=["tool_missing"],
            created_at=datetime.now(timezone.utc),
        )
        output = json.loads(d.model_dump_json())
        schema = json.load(open("schemas/compatibility-decision.schema.json"))
        jsonschema.validate(output, schema)

    def test_invalid_decision(self):
        with pytest.raises(Exception):
            CompatibilityDecision(
                decision_id="rdc_bad",
                subject=DecisionSubject(type="episode", id="ep_bad"),
                old_manifest_id="amf_old",
                target_manifest_id="amf_new",
                decision="invalid_decision",
                reason_codes=[],
                created_at=datetime.now(timezone.utc),
            )


class TestCompatibilityBatch:
    def test_parse(self):
        batch = CompatibilityBatch(
            batch_id="rcb_001",
            old_manifest_id="amf_old",
            target_manifest_id="amf_new",
            created_at=datetime.now(timezone.utc),
            summary=CompatibilityBatchSummary(
                total_episodes=10000, keep=7200, repair=800, replay=1500, drop=500
            ),
            classification_rules=[
                ClassificationRule(
                    rule_id="rule_01",
                    condition="tool_surface_unchanged AND prompt_surface_unchanged",
                    decision="keep",
                    matched_count=7200,
                ),
                ClassificationRule(
                    rule_id="rule_02",
                    condition="tool_missing:search_population",
                    decision="replay",
                    reason_codes=["tool_missing"],
                    matched_count=1500,
                ),
            ],
        )
        assert batch.summary.total_episodes == 10000
        assert len(batch.classification_rules) == 2

    def test_summary_fields(self):
        s = CompatibilityBatchSummary(
            total_episodes=100, keep=60, repair=20, replay=15, drop=5
        )
        assert s.keep + s.repair + s.replay + s.drop == s.total_episodes


class TestReplayJob:
    def test_parse_minimal(self):
        job = ReplayJob(
            replay_job_id="rpj_001",
            task_id="tsk_001",
            target_manifest_id="amf_new",
            mode="customer_runtime",
            priority="normal",
            replay_input=ReplayInput(
                messages=[Message(role="user", content="Hello")]
            ),
            created_at=datetime.now(timezone.utc),
        )
        assert job.kind == "replay_job"
        assert job.mode == "customer_runtime"

    def test_validates_against_schema(self):
        import jsonschema

        job = ReplayJob(
            replay_job_id="rpj_002",
            task_id="tsk_002",
            target_manifest_id="amf_new",
            mode="offline_batch",
            priority="high",
            replay_input=ReplayInput(
                messages=[Message(role="user", content="What is NVDA market cap?")]
            ),
            created_at=datetime.now(timezone.utc),
        )
        output = json.loads(job.model_dump_json())
        schema = json.load(open("schemas/replay-job.schema.json"))
        jsonschema.validate(output, schema)

    def test_invalid_mode(self):
        with pytest.raises(Exception):
            ReplayJob(
                replay_job_id="rpj_bad",
                task_id="tsk_bad",
                target_manifest_id="amf_new",
                mode="invalid_mode",
                replay_input=ReplayInput(
                    messages=[Message(role="user", content="test")]
                ),
                created_at=datetime.now(timezone.utc),
            )


class TestReplayResult:
    def test_parse(self):
        result = ReplayResult(
            replay_job_id="rpj_001",
            status="completed",
            target_manifest_id="amf_new",
            replayed_episode_id="ep_new_789",
            replayability="fully_replayable",
            completed_at=datetime.now(timezone.utc),
        )
        assert result.kind == "replay_result"
        assert result.status == "completed"

    def test_all_statuses(self):
        for status in ["queued", "running", "completed", "failed", "cancelled"]:
            r = ReplayResult(
                replay_job_id="rpj_test",
                status=status,
                target_manifest_id="amf_test",
            )
            assert r.status == status
