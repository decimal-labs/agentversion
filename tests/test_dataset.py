"""Tests for dataset models (Task, Episode, Step, DatasetSnapshot)."""

import json
from datetime import datetime, timezone

from agentversion.dataset import (
    DatasetSnapshot,
    Episode,
    EpisodeResult,
    ItemRef,
    Message,
    SelectionPolicy,
    SnapshotLineage,
    Step,
    StepActor,
    StepInput,
    StepOutput,
    Task,
    TaskInput,
    ToolCallOutput,
)


class TestTask:
    def test_parse_minimal(self):
        t = Task(
            task_id="tsk_001",
            created_at=datetime.now(timezone.utc),
            input=TaskInput(
                messages=[Message(role="user", content="Hello")]
            ),
        )
        assert t.kind == "task"
        assert len(t.input.messages) == 1

    def test_multi_turn(self):
        t = Task(
            task_id="tsk_002",
            created_at=datetime.now(timezone.utc),
            input=TaskInput(
                messages=[
                    Message(role="user", content="What is NVDA?"),
                    Message(role="assistant", content="NVDA is Nvidia..."),
                    Message(role="user", content="What is its market cap?"),
                ]
            ),
            metadata={"turn_count": 3, "is_multi_turn": True},
        )
        assert len(t.input.messages) == 3
        assert t.metadata["is_multi_turn"] is True

    def test_roundtrip(self):
        t = Task(
            task_id="tsk_003",
            created_at=datetime.now(timezone.utc),
            input=TaskInput(messages=[Message(role="user", content="test")]),
            tags=["finance", "evergreen"],
        )
        output = json.loads(t.model_dump_json())
        t2 = Task.model_validate(output)
        assert t2.task_id == t.task_id
        assert t2.tags == ["finance", "evergreen"]

    def test_validates_against_schema(self):
        import jsonschema

        t = Task(
            task_id="tsk_004",
            created_at=datetime.now(timezone.utc),
            input=TaskInput(messages=[Message(role="user", content="test")]),
        )
        output = json.loads(t.model_dump_json())
        schema = json.load(open("schemas/task.schema.json"))
        jsonschema.validate(output, schema)


class TestEpisode:
    def test_parse(self):
        ep = Episode(
            episode_id="ep_001",
            task_id="tsk_001",
            status="success",
            step_ids=["stp_1", "stp_2"],
        )
        assert ep.kind == "episode"
        assert ep.status == "success"
        assert len(ep.step_ids) == 2

    def test_with_result(self):
        ep = Episode(
            episode_id="ep_002",
            task_id="tsk_001",
            status="success",
            result=EpisodeResult(
                final_output={"text": "Nvidia market cap is..."},
                success_label=True,
            ),
        )
        assert ep.result.success_label is True


class TestStep:
    def test_parse_llm_call(self):
        s = Step(
            step_id="stp_001",
            episode_id="ep_001",
            index=1,
            step_type="llm_call",
            actor=StepActor(type="agent", name="finance_subagent"),
            input=StepInput(
                messages=[Message(role="user", content="What is NVDA?")]
            ),
            output=StepOutput(
                tool_call=ToolCallOutput(
                    name="get_market_cap", arguments={"ticker": "NVDA"}
                )
            ),
        )
        assert s.step_type == "llm_call"
        assert s.output.tool_call.name == "get_market_cap"

    def test_all_step_types(self):
        from agentversion.dataset import STEP_TYPES

        for st in STEP_TYPES:
            s = Step(step_id="stp", episode_id="ep", index=0, step_type=st)
            assert s.step_type == st


class TestDatasetSnapshot:
    def test_parse(self):
        snap = DatasetSnapshot(
            snapshot_id="dss_001",
            name="finance_sft_2026_03",
            dataset_type="sft",
            created_at=datetime.now(timezone.utc),
            selection_policy=SelectionPolicy(
                source_types=["production", "replay"],
                required_episode_status="success",
            ),
            item_refs=[
                ItemRef(task_id="tsk_01", episode_id="ep_01", step_id="stp_1"),
            ],
            lineage=SnapshotLineage(
                built_from_manifest_ids=["amf_001"],
            ),
        )
        assert snap.kind == "dataset_snapshot"
        assert snap.dataset_type == "sft"
        assert len(snap.item_refs) == 1

    def test_roundtrip(self):
        snap = DatasetSnapshot(
            snapshot_id="dss_002",
            name="test_snap",
            dataset_type="eval",
            created_at=datetime.now(timezone.utc),
        )
        output = json.loads(snap.model_dump_json())
        snap2 = DatasetSnapshot.model_validate(output)
        assert snap2.snapshot_id == snap.snapshot_id
