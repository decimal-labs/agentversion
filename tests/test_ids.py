"""Tests for the canonical ID scheme (§3b, added in v0.4.0)."""

from __future__ import annotations

import re

import pytest

from agentversion.ids import (
    ID_PREFIXES,
    is_canonical_id,
    mint_id,
    parse_id,
    validate_id,
)


class TestMintId:
    def test_mint_returns_prefixed_id_for_each_kind(self):
        for kind, prefix in ID_PREFIXES.items():
            mid = mint_id(kind)
            assert mid.startswith(prefix + "_"), f"{kind}: {mid}"

    def test_mint_produces_canonical_form(self):
        mid = mint_id("agent_manifest")
        assert is_canonical_id(mid)
        prefix, ulid = parse_id(mid)  # type: ignore[misc]
        assert prefix == "amf"
        assert len(ulid) == 26
        # Crockford base32: no I, L, O, U
        assert re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", ulid)

    def test_mint_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="unknown kind"):
            mint_id("nonexistent_kind")

    def test_mint_is_unique(self):
        ids = {mint_id("task") for _ in range(100)}
        # 100 calls with 80 bits of randomness → effectively never collide
        assert len(ids) == 100

    def test_mint_is_time_sortable(self):
        import time

        a = mint_id("task")
        time.sleep(0.01)
        b = mint_id("task")
        # ULIDs are big-endian timestamp-first, so lexical < works
        assert a < b


class TestParseId:
    def test_parse_canonical(self):
        assert parse_id("amf_01HZK1A2B3C4D5E6F7G8H9J0K1") == (
            "amf",
            "01HZK1A2B3C4D5E6F7G8H9J0K1",
        )

    def test_parse_slug_returns_none(self):
        # Slug form is permissive but not canonical, so parse_id rejects it.
        assert parse_id("amf_finance_v3") is None

    def test_parse_garbage(self):
        assert parse_id("not an id") is None
        assert parse_id("") is None
        assert parse_id("amf_") is None
        assert parse_id("_01HZK1A2B3C4D5E6F7G8H9J0K1") is None


class TestIsCanonical:
    def test_canonical_passes(self):
        assert is_canonical_id(mint_id("episode"))

    def test_slug_not_canonical(self):
        assert not is_canonical_id("amf_finance_v3")

    def test_short_ulid_not_canonical(self):
        # 25 chars instead of 26
        assert not is_canonical_id("amf_01HZK1A2B3C4D5E6F7G8H9J0K")

    def test_long_ulid_not_canonical(self):
        # 27 chars
        assert not is_canonical_id("amf_01HZK1A2B3C4D5E6F7G8H9J0K11")


class TestValidateId:
    def test_canonical_passes(self):
        assert validate_id("amf_01HZK1A2B3C4D5E6F7G8H9J0K1")

    def test_slug_fails(self):
        with pytest.raises(ValueError, match="not canonical"):
            validate_id("amf_finance_v3")

    def test_wrong_prefix_raises(self):
        with pytest.raises(ValueError, match="prefix 'amf'"):
            validate_id(
                "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
                expected_kind="task",
            )

    def test_unknown_expected_kind_raises(self):
        with pytest.raises(ValueError, match="unknown expected_kind"):
            validate_id(
                "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
                expected_kind="something_made_up",
            )

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            validate_id("")

    def test_correct_prefix_for_each_kind(self):
        for kind in ID_PREFIXES:
            mid = mint_id(kind)
            assert validate_id(mid, expected_kind=kind)


class TestValidatorIntegration:
    """The semantic validator should warn (or error) on non-canonical IDs."""

    def _minimal(self, **overrides) -> dict:
        base = {
            "spec_version": "0.4.0",
            "kind": "agent_manifest",
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "agent_name": "test",
            "version_label": "v1",
            "created_at": "2026-01-01T00:00:00Z",
            "identity": {
                "overall_hash": "sha256:abc",
                "hash_algorithm": "jcs-sha256",
            },
            "contract": {
                "prompt_stack": {},
                "model_runtime": {"provider": "openai", "model": "gpt-4o"},
                "tool_registry": {
                    "registry_version": "1",
                    "registry_hash": "sha256:reg",
                    "tools": [],
                },
                "workflow": {"graph_name": "g"},
                "output_contract": {
                    "version": "1",
                    "schema_hash": "sha256:o",
                    "format": "text",
                    "strict": False,
                },
            },
        }
        base.update(overrides)
        return base

    def test_canonical_id_no_warning(self):
        from agentversion.validator import validate_manifest

        result = validate_manifest(self._minimal(), check_hash=False)
        id_issues = [w for w in result.issues if w.code in {"malformed_id", "wrong_id_prefix"}]
        assert id_issues == []

    def test_slug_id_errors(self):
        from agentversion.validator import validate_manifest

        result = validate_manifest(
            self._minimal(manifest_id="amf_finance_v3"), check_hash=False
        )
        assert result.valid is False
        codes = {w.code for w in result.errors}
        assert "malformed_id" in codes

    def test_wrong_prefix_errors(self):
        from agentversion.validator import validate_manifest

        result = validate_manifest(
            self._minimal(manifest_id="tsk_01HZK1A2B3C4D5E6F7G8H9J0K1"),
            check_hash=False,
        )
        codes = {w.code for w in result.errors}
        assert "wrong_id_prefix" in codes


class TestCheckObjectIdsNonManifest:
    """check_object_ids() should enforce IDs on every spec kind, not just manifests."""

    def test_task_valid(self):
        from agentversion.ids import check_object_ids

        issues = check_object_ids(
            {"kind": "task", "task_id": "tsk_01HZK1A2B3C4D5E6F7G8H9J0K1"}
        )
        assert issues == []

    def test_task_wrong_prefix(self):
        from agentversion.ids import check_object_ids

        issues = check_object_ids(
            {"kind": "task", "task_id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K1"}
        )
        codes = {i[1] for i in issues}
        assert "wrong_id_prefix" in codes

    def test_episode_validates_task_foreign_ref(self):
        from agentversion.ids import check_object_ids

        issues = check_object_ids({
            "kind": "episode",
            "episode_id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "task_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K2",  # wrong — manifest prefix in task ref
            "manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
        })
        # The episode_id and manifest_id are valid; task_id has wrong prefix
        codes = [(i[1], i[3]) for i in issues]
        assert ("wrong_id_prefix", "task_id") in codes
        # episode_id and manifest_id should NOT appear in issues
        paths_with_issues = {i[3] for i in issues}
        assert "episode_id" not in paths_with_issues
        assert "manifest_id" not in paths_with_issues

    def test_dataset_snapshot_array_refs(self):
        from agentversion.ids import check_object_ids

        issues = check_object_ids({
            "kind": "dataset_snapshot",
            "snapshot_id": "dss_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "item_refs": [
                {"task_id": "tsk_01HZK1A2B3C4D5E6F7G8H9J0K2",
                 "episode_id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K3"},
                {"task_id": "tsk_finance_v1"},  # slug — malformed_id
                {"task_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K4"},  # wrong prefix
            ],
            "lineage": {
                "built_from_manifest_ids": ["amf_01HZK1A2B3C4D5E6F7G8H9J0K5"],
            },
        })
        codes_and_paths = [(i[1], i[3]) for i in issues]
        assert ("malformed_id", "item_refs[1].task_id") in codes_and_paths
        assert ("wrong_id_prefix", "item_refs[2].task_id") in codes_and_paths
        # the canonical refs and the lineage manifest id should NOT appear
        assert ("wrong_id_prefix", "item_refs[0].task_id") not in codes_and_paths

    def test_compatibility_decision_subject_prefix(self):
        """subject.id's expected prefix is determined by subject.type."""
        from agentversion.ids import check_object_ids

        # subject.type=episode, subject.id has episode prefix → OK
        issues = check_object_ids({
            "kind": "compatibility_decision",
            "decision_id": "cdc_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "old_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K2",
            "target_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
            "subject": {"type": "episode", "id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K4"},
        })
        assert issues == []

        # subject.type=episode, subject.id has task prefix → wrong_id_prefix
        issues = check_object_ids({
            "kind": "compatibility_decision",
            "decision_id": "cdc_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "old_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K2",
            "target_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
            "subject": {"type": "episode", "id": "tsk_01HZK1A2B3C4D5E6F7G8H9J0K4"},
        })
        codes_and_paths = [(i[1], i[3]) for i in issues]
        assert ("wrong_id_prefix", "subject.id") in codes_and_paths

    def test_dataset_item_subject_empty_id_flagged(self):
        """subject.type=dataset_item has no ID prefix, but a blank id must fail."""
        from agentversion.ids import check_object_ids

        issues = check_object_ids({
            "kind": "compatibility_decision",
            "decision_id": "cdc_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "old_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K2",
            "target_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
            "subject": {"type": "dataset_item", "id": "  "},
        })
        codes_and_paths = [(i[1], i[3]) for i in issues]
        assert ("empty_id", "subject.id") in codes_and_paths

    def test_dataset_item_subject_nonempty_id_ok(self):
        """A non-empty dataset_item id has no prefix contract, so it passes."""
        from agentversion.ids import check_object_ids

        issues = check_object_ids({
            "kind": "compatibility_decision",
            "decision_id": "cdc_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "old_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K2",
            "target_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K3",
            "subject": {"type": "dataset_item", "id": "row-42"},
        })
        assert issues == []

    def test_replay_job_all_fields(self):
        from agentversion.ids import check_object_ids

        issues = check_object_ids({
            "kind": "replay_job",
            "replay_job_id": "rpj_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "task_id": "tsk_01HZK1A2B3C4D5E6F7G8H9J0K2",
            "source_episode_id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K3",
            "target_manifest_id": "amf_01HZK1A2B3C4D5E6F7G8H9J0K4",
            "lineage": {"requested_from_episode_id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K5"},
        })
        assert issues == []

    def test_unknown_kind_returns_empty(self):
        from agentversion.ids import check_object_ids

        # Unknown kinds shouldn't error — just no checks run.
        issues = check_object_ids({"kind": "some_future_kind", "foo": "bar"})
        assert issues == []

    def test_slug_is_error(self):
        from agentversion.ids import check_object_ids

        data = {"kind": "task", "task_id": "tsk_my_task_v3"}
        issues = check_object_ids(data)
        sevs = {i[0] for i in issues}
        codes = {i[1] for i in issues}
        assert sevs == {"error"}
        assert "malformed_id" in codes

    def test_missing_optional_fields_are_skipped(self):
        from agentversion.ids import check_object_ids

        # episode without lineage.parent_episode_id — no issue
        issues = check_object_ids({
            "kind": "episode",
            "episode_id": "ep_01HZK1A2B3C4D5E6F7G8H9J0K1",
            "task_id": "tsk_01HZK1A2B3C4D5E6F7G8H9J0K2",
        })
        assert issues == []
