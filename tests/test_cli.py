"""Tests for agentversion CLI."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

from agentversion import __version__
from agentversion.cli import cli
from agentversion.ids import mint_id

V1 = "examples/manifest/finance-agent-v1.json"
V2 = "examples/manifest/finance-agent-v2.json"


def _pyproject_version() -> str:
    """The package version as declared in pyproject.toml — the single source of truth.

    Read with a regex rather than tomllib so this works on Python 3.10, which the
    package still supports and which has no stdlib TOML parser.
    """
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject.read_text())
    assert match, "no version declared in pyproject.toml"
    return match.group(1)


def test_version():
    """Installed package metadata must agree with pyproject.toml.

    This asserts the INVARIANT rather than a literal. An earlier version of this
    test hard-coded the number and had to be hand-bumped on every release; it was
    not, so it sat asserting 0.1.0 while the package shipped 0.2.2 — green in a
    stale local venv (whose dist-info still said 0.1.0) and red in every fresh
    install, which is the worst possible direction for a test to fail in.

    Note this is the PACKAGE version, deliberately independent of the SPEC version
    (agentversion.SPEC_VERSION) — the wire format is frozen at 1.0 while the
    Python package continues to evolve.
    """
    assert __version__ == _pyproject_version()


def test_cli_help():
    """CLI --help should succeed."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "AgentVersion" in result.output


def test_cli_version():
    """CLI --version should show version."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert _pyproject_version() in result.output  # package version (see test_version)


def test_validate_valid_manifest():
    """validate should succeed on a valid example manifest."""
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "examples/manifest/finance-agent-v1.json"])
    assert result.exit_code == 0
    assert "✓" in result.output or "valid" in result.output.lower()


def test_validate_invalid_file(tmp_path):
    """validate should fail on invalid JSON."""
    bad = tmp_path / "bad.json"
    bad.write_text('{"kind": "wrong"}')
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(bad)])
    assert result.exit_code == 1


def test_hash_manifest():
    """hash should print a sha256 hash."""
    runner = CliRunner()
    result = runner.invoke(cli, ["hash", "examples/manifest/finance-agent-v1.json"])
    assert result.exit_code == 0
    assert "sha256:" in result.output


def test_hash_matches_declared():
    """hash output should match the declared hash in the example."""
    with open("examples/manifest/finance-agent-v1.json") as f:
        data = json.load(f)
    declared = data["identity"]["overall_hash"]

    runner = CliRunner()
    result = runner.invoke(cli, ["hash", "examples/manifest/finance-agent-v1.json"])
    assert declared in result.output


def test_init_then_validate():
    """A manifest produced by `init` must pass `validate` (canonical id + spec_version)."""
    from agentversion.constants import SPEC_VERSION
    from agentversion.ids import is_canonical_id

    runner = CliRunner()
    with runner.isolated_filesystem():
        init_result = runner.invoke(cli, ["init"], input="testagent\nv1\nopenai\ngpt-4o\n")
        assert init_result.exit_code == 0, init_result.output

        with open("testagent-manifest.json") as f:
            data = json.load(f)
        assert is_canonical_id(data["manifest_id"])
        assert data["manifest_id"].startswith("amf_")
        assert data["spec_version"] == SPEC_VERSION

        validate_result = runner.invoke(cli, ["validate", "testagent-manifest.json"])
        assert validate_result.exit_code == 0, validate_result.output


class TestDiff:
    def test_text_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", V1, V2])
        assert result.exit_code == 0, result.output
        # v1→v2 has 5 breaking, 2 non-breaking surfaces.
        assert "Breaking: 5" in result.output
        assert "output_contract" in result.output

    def test_json_output(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", V1, V2, "--json"])
        assert result.exit_code == 0, result.output
        assert '"kind"' in result.output and "manifest_diff" in result.output
        assert "changed_surfaces" in result.output

    def test_compat_recommendation(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", V1, V2, "--compat"])
        assert result.exit_code == 0, result.output
        assert "Recommendation" in result.output

    def test_fail_on_breaking_exits_nonzero(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", V1, V2, "--fail-on-breaking"])
        assert result.exit_code == 1

    def test_identical_manifests_no_changes(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", V1, V1])
        assert result.exit_code == 0, result.output
        assert "No changes detected" in result.output

    def test_identical_with_fail_on_breaking_still_passes(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["diff", V1, V1, "--fail-on-breaking"])
        assert result.exit_code == 0, result.output


class TestUpgrade:
    def test_minor_bump_to_stdout(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["upgrade", V1, "--to", "1.1.0"])
        assert result.exit_code == 0, result.output
        assert "1.1.0" in result.output

    def test_refuses_downgrade(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["upgrade", V1, "--to", "0.9.0"])
        assert result.exit_code == 2
        assert "downgrade" in result.output.lower()

    def test_refuses_cross_major(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["upgrade", V1, "--to", "2.0.0"])
        assert result.exit_code == 2
        assert "major" in result.output.lower()

    def test_rejects_bad_semver(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["upgrade", V1, "--to", "1.1"])
        assert result.exit_code == 2

    def test_in_place_rewrites_file(self, tmp_path):
        src = json.load(open(V1))
        target = tmp_path / "m.json"
        target.write_text(json.dumps(src))
        runner = CliRunner()
        result = runner.invoke(cli, ["upgrade", str(target), "--to", "1.1.0", "--in-place"])
        assert result.exit_code == 0, result.output
        assert json.loads(target.read_text())["spec_version"] == "1.1.0"


class TestDecisionCli:
    def test_generate_emits_decision(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["decision", "generate", V1, V2, "--subject-id", "ep_x"]
        )
        assert result.exit_code == 0, result.output
        assert "compatibility_decision" in result.output
        assert '"decision"' in result.output

    def test_generate_rejects_bad_subject_type(self):
        runner = CliRunner()
        result = runner.invoke(
            cli, ["decision", "generate", V1, V2, "--subject-type", "bogus"]
        )
        # click.Choice rejects the value before the command body runs.
        assert result.exit_code == 2

    def test_validate_canonical_decision(self, tmp_path):
        from agentversion.decision import CompatibilityDecision, DecisionSubject

        d = CompatibilityDecision(
            decision_id=mint_id("compatibility_decision"),
            subject=DecisionSubject(type="episode", id=mint_id("episode")),
            old_manifest_id=mint_id("agent_manifest"),
            target_manifest_id=mint_id("agent_manifest"),
            decision="replay",
            reason_codes=["tool_missing"],
            created_at=datetime.now(timezone.utc),
        )
        f = tmp_path / "dec.json"
        f.write_text(d.model_dump_json())
        runner = CliRunner()
        result = runner.invoke(cli, ["decision", "validate", str(f)])
        assert result.exit_code == 0, result.output
        assert "replay" in result.output

    def test_validate_noncanonical_id_fails(self, tmp_path):
        # Documents the rough edge: `decision generate --subject-id <free text>`
        # produces non-canonical IDs, which `decision validate` rejects.
        from agentversion.decision import CompatibilityDecision, DecisionSubject

        d = CompatibilityDecision(
            decision_id="cdc_auto_ep_x",
            subject=DecisionSubject(type="episode", id="ep_x"),
            old_manifest_id=mint_id("agent_manifest"),
            target_manifest_id=mint_id("agent_manifest"),
            decision="replay",
            created_at=datetime.now(timezone.utc),
        )
        f = tmp_path / "dec.json"
        f.write_text(d.model_dump_json())
        runner = CliRunner()
        result = runner.invoke(cli, ["decision", "validate", str(f)])
        assert result.exit_code == 1
        assert "canonical" in result.output.lower()


class TestReplayCli:
    def test_validate_minimal_job(self, tmp_path):
        from agentversion._shared import Message
        from agentversion.replay import ReplayInput, ReplayJob

        job = ReplayJob(
            replay_job_id=mint_id("replay_job"),
            task_id=mint_id("task"),
            target_manifest_id=mint_id("agent_manifest"),
            mode="offline_batch",
            replay_input=ReplayInput(messages=[Message(role="user", content="hi")]),
            created_at=datetime.now(timezone.utc),
        )
        f = tmp_path / "job.json"
        f.write_text(job.model_dump_json())
        runner = CliRunner()
        result = runner.invoke(cli, ["replay", "validate", str(f)])
        assert result.exit_code == 0, result.output
        assert "offline_batch" in result.output

    def test_validate_rejects_missing_required(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text(json.dumps({"kind": "replay_job", "replay_job_id": "rpj_x"}))
        runner = CliRunner()
        result = runner.invoke(cli, ["replay", "validate", str(f)])
        assert result.exit_code == 1


class TestDatasetCli:
    def test_validate_task(self, tmp_path):
        from agentversion._shared import Message
        from agentversion.dataset import Task, TaskInput

        t = Task(
            task_id=mint_id("task"),
            created_at=datetime.now(timezone.utc),
            input=TaskInput(messages=[Message(role="user", content="hi")]),
        )
        f = tmp_path / "task.json"
        f.write_text(t.model_dump_json())
        runner = CliRunner()
        result = runner.invoke(cli, ["dataset", "validate", str(f)])
        assert result.exit_code == 0, result.output
        assert "task" in result.output.lower()

    def test_validate_unknown_kind(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text(json.dumps({"kind": "bogus"}))
        runner = CliRunner()
        result = runner.invoke(cli, ["dataset", "validate", str(f)])
        assert result.exit_code == 1
        assert "Unknown kind" in result.output
