"""CLI entry point for agentversion."""

import json
from datetime import datetime, timezone
from typing import Any, Literal, cast

import click
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from agentversion import __version__
from agentversion.constants import SPEC_VERSION

console = Console()


def _print_id_issues(data: dict[str, Any], kind: str) -> int:
    """Run ID checks and print them. Returns the number of errors (so the
    caller can ``raise SystemExit`` if non-zero)."""
    from agentversion.ids import check_object_ids

    errors = 0
    for sev, code, message, path in check_object_ids(data, kind=kind):
        icon = "[red]✗[/red]" if sev == "error" else "[yellow]⚠[/yellow]"
        console.print(f"  {icon} [{code}] at {path}: {message}")
        if sev == "error":
            errors += 1
    return errors


@click.group()
@click.version_option(version=__version__, prog_name="agentversion")
def cli() -> None:
    """AgentVersion — CLI tools.

    An open specification for versioning agent runtimes
    and keeping datasets valid.
    """
    pass


@cli.command()
@click.argument("manifest_file", type=click.Path(exists=True))
def validate(manifest_file: str) -> None:
    """Validate a manifest file against the spec."""
    from agentversion.validator import Severity, validate_manifest_file

    result = validate_manifest_file(manifest_file)

    if result.valid and not result.warnings:
        console.print(f"[green]✓[/green] {manifest_file} is valid")
        if result.manifest:
            console.print(f"  agent: [bold]{result.manifest.agent_name}[/bold]")
            console.print(f"  version: {result.manifest.version_label}")
            console.print(f"  hash: {result.manifest.identity.overall_hash[:24]}...")
        return

    for issue in result.issues:
        if issue.severity == Severity.ERROR:
            icon = "[red]✗[/red]"
        elif issue.severity == Severity.WARNING:
            icon = "[yellow]⚠[/yellow]"
        else:
            icon = "[blue]ℹ[/blue]"

        path_str = f" at {issue.path}" if issue.path else ""
        console.print(f"  {icon} [{issue.code}]{path_str}: {issue.message}")

    if result.valid:
        console.print(f"\n[green]✓[/green] {manifest_file} is valid (with {len(result.warnings)} warning(s))")
    else:
        console.print(f"\n[red]✗[/red] {manifest_file} is invalid ({len(result.errors)} error(s))")
        raise SystemExit(1)


@cli.command()
@click.argument("old_manifest", type=click.Path(exists=True))
@click.argument("new_manifest", type=click.Path(exists=True))
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--fail-on-breaking", is_flag=True, help="Exit with code 1 if breaking changes found")
@click.option("--compat", is_flag=True, help="Include compatibility recommendation")
def diff(old_manifest: str, new_manifest: str, output_json: bool, fail_on_breaking: bool, compat: bool) -> None:
    """Diff two manifest files and classify changes."""
    from agentversion.compatibility import classify_compatibility
    from agentversion.diff import diff_manifests

    with open(old_manifest) as f:
        old_data = json.load(f)
    with open(new_manifest) as f:
        new_data = json.load(f)

    result = diff_manifests(old_data, new_data)

    if output_json:
        output = json.loads(result.model_dump_json())
        if compat:
            report = classify_compatibility(result)
            output["compatibility"] = json.loads(report.model_dump_json())
        console.print_json(json.dumps(output, indent=2))
    else:
        if not result.changed_surfaces:
            console.print("[green]✓[/green] No changes detected")
            return

        table = Table(title="Manifest Diff")
        table.add_column("Surface", style="bold")
        table.add_column("Change Type")
        table.add_column("Details")

        for change in result.changed_surfaces:
            style = "red" if change.change_type == "breaking" else "green"
            table.add_row(
                change.surface,
                f"[{style}]{change.change_type}[/{style}]",
                "\n".join(change.details),
            )
        console.print(table)
        console.print(
            f"\n  Breaking: {result.summary.breaking_surfaces}  "
            f"Non-breaking: {result.summary.non_breaking_surfaces}"
        )

        if compat:
            report = classify_compatibility(result)
            console.print(f"\n  Recommendation: [bold]{report.recommended_decision}[/bold]")
            console.print(f"  {report.summary}")

    if fail_on_breaking and result.summary.breaking_surfaces > 0:
        raise SystemExit(1)


@cli.command()
def init() -> None:
    """Initialize a new manifest file interactively."""
    from agentversion.hasher import compute_and_set_hashes
    from agentversion.ids import mint_id

    agent_name = click.prompt("Agent name", type=str)
    version_label = click.prompt("Version label", default="v1")
    provider = click.prompt("Model provider (e.g. openai, anthropic, google)", type=str)
    model = click.prompt("Model name (e.g. gpt-4o, claude-opus-4, gemini-2.0-flash)", type=str)

    manifest = {
        "spec_version": SPEC_VERSION,
        "kind": "agent_manifest",
        "manifest_id": mint_id("agent_manifest"),
        "agent_name": agent_name,
        "version_label": version_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": f"Manifest for {agent_name} {version_label}",
        "tags": [],
        "identity": {
            "overall_hash": "PLACEHOLDER",
            "hash_algorithm": "jcs-sha256",
        },
        "contract": {
            "prompt_stack": {
                "system_prompt": {
                    "id": f"prompt_system_{agent_name}",
                    "version": "1",
                    "hash": "sha256:REPLACE_WITH_ACTUAL_HASH",
                },
                "reasoning_policy": "hidden",
            },
            "model_runtime": {
                "provider": provider,
                "model": model,
            },
            "tool_registry": {
                "registry_version": "1",
                "registry_hash": "sha256:REPLACE_WITH_ACTUAL_HASH",
                "tools": [],
            },
            "workflow": {
                "graph_name": f"{agent_name}-graph",
                "graph_version": "1",
            },
            "output_contract": {
                "version": "1",
                "schema_hash": "sha256:REPLACE_WITH_ACTUAL_HASH",
                "format": "text",
                "strict": False,
            },
            "guardrails": None,
        },
        "extensions": {},
    }

    compute_and_set_hashes(manifest)

    output_file = f"{agent_name}-manifest.json"
    with open(output_file, "w") as f:
        json.dump(manifest, f, indent=2)
    console.print(f"[green]✓[/green] Created {output_file}")
    console.print(f"  hash: {manifest['identity']['overall_hash']}")


@cli.command()
@click.argument("manifest_file", type=click.Path(exists=True))
def hash(manifest_file: str) -> None:
    """Compute the canonical hash of a manifest."""
    from agentversion.hasher import hash_manifest

    with open(manifest_file) as f:
        data = json.load(f)

    computed_hash = hash_manifest(data)
    console.print(computed_hash)

    existing = data.get("identity", {}).get("overall_hash")
    if existing and existing != computed_hash:
        console.print(f"[yellow]⚠[/yellow] Declared hash differs: {existing}")


@cli.command()
@click.argument("manifest_file", type=click.Path(exists=True))
@click.option("--to", "target_version", required=True, help="Target spec version (e.g. 1.1.0)")
@click.option("--in-place", is_flag=True, help="Rewrite the input file instead of printing to stdout")
def upgrade(manifest_file: str, target_version: str, in_place: bool) -> None:
    """Upgrade a manifest to a newer spec version.

    Within a major version there are no field-level migrations required, so
    this is an identity upgrade: parse, set spec_version, re-emit. Refuses to
    downgrade or cross major-version boundaries.
    """
    import re

    semver_re = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
    if not semver_re.match(target_version):
        console.print(f"[red]✗[/red] --to must be MAJOR.MINOR.PATCH (got {target_version!r})")
        raise SystemExit(2)

    with open(manifest_file) as f:
        data = json.load(f)

    current = data.get("spec_version", "0.0.0")
    m_cur = semver_re.match(current)
    m_tgt = semver_re.match(target_version)
    if not m_cur:
        console.print(f"[red]✗[/red] manifest has invalid spec_version {current!r}")
        raise SystemExit(2)

    cur_tuple = tuple(int(x) for x in m_cur.groups())
    tgt_tuple = tuple(int(x) for x in m_tgt.groups())  # type: ignore[union-attr]

    if tgt_tuple < cur_tuple:
        console.print(f"[red]✗[/red] refuse to downgrade ({current} → {target_version})")
        raise SystemExit(2)
    if tgt_tuple[0] != cur_tuple[0]:
        console.print(
            f"[red]✗[/red] cross-major upgrade not supported "
            f"({current} → {target_version}); see CHANGELOG for the migration path"
        )
        raise SystemExit(2)

    data["spec_version"] = target_version

    if in_place:
        with open(manifest_file, "w") as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]✓[/green] {manifest_file}: {current} → {target_version}")
    else:
        console.print_json(json.dumps(data, indent=2))


# -- Sub-command groups for other spec objects --


@cli.group()
def decision() -> None:
    """Compatibility decision commands."""
    pass


@decision.command("validate")
@click.argument("decision_file", type=click.Path(exists=True))
def decision_validate(decision_file: str) -> None:
    """Validate a compatibility decision file."""
    from agentversion.decision import CompatibilityDecision

    with open(decision_file) as f:
        data = json.load(f)
    try:
        d = CompatibilityDecision.model_validate(data)
        console.print(f"[green]✓[/green] Valid compatibility decision: {d.decision}")
        console.print(f"  subject: {d.subject.type}/{d.subject.id}")
        if d.reason_codes:
            console.print(f"  reasons: {', '.join(d.reason_codes)}")
    except Exception as e:
        console.print(f"[red]✗[/red] Invalid compatibility decision: {e}")
        raise SystemExit(1)

    if _print_id_issues(data, "compatibility_decision") > 0:
        raise SystemExit(1)


@decision.command("generate")
@click.argument("old_manifest", type=click.Path(exists=True))
@click.argument("new_manifest", type=click.Path(exists=True))
@click.option(
    "--subject-type",
    type=click.Choice(["task", "episode", "step", "dataset_item"]),
    default="episode",
    help="Subject type",
)
@click.option("--subject-id", default="ep_unknown", help="Subject ID")
def decision_generate(old_manifest: str, new_manifest: str, subject_type: str, subject_id: str) -> None:
    """Auto-generate a compatibility decision from two manifests."""
    from datetime import timezone

    from agentversion.compatibility import classify_compatibility
    from agentversion.decision import CompatibilityDecision, DecisionSubject
    from agentversion.diff import diff_manifests
    from agentversion.ids import mint_id

    with open(old_manifest) as f:
        old_data = json.load(f)
    with open(new_manifest) as f:
        new_data = json.load(f)

    diff_result = diff_manifests(old_data, new_data)
    report = classify_compatibility(diff_result)

    cd = CompatibilityDecision(
        decision_id=mint_id("compatibility_decision"),
        subject=DecisionSubject(
            type=cast(Literal["task", "episode", "step", "dataset_item"], subject_type),
            id=subject_id,
        ),
        old_manifest_id=old_data.get("manifest_id", "unknown"),
        target_manifest_id=new_data.get("manifest_id", "unknown"),
        decision=report.recommended_decision,
        reason_codes=report.reason_codes,
        created_at=datetime.now(timezone.utc),
    )

    console.print_json(cd.model_dump_json(indent=2))


@cli.group()
def replay() -> None:
    """Replay job commands."""
    pass


@replay.command("validate")
@click.argument("job_file", type=click.Path(exists=True))
def replay_validate(job_file: str) -> None:
    """Validate a replay job file."""
    from agentversion.replay import ReplayJob

    with open(job_file) as f:
        data = json.load(f)
    try:
        job = ReplayJob.model_validate(data)
        console.print(f"[green]✓[/green] Valid replay job: {job.replay_job_id}")
        console.print(f"  mode: {job.mode}  priority: {job.priority}")
        console.print(f"  target: {job.target_manifest_id}")
    except Exception as e:
        console.print(f"[red]✗[/red] Invalid replay job: {e}")
        raise SystemExit(1)

    if _print_id_issues(data, "replay_job") > 0:
        raise SystemExit(1)


@cli.group()
def dataset() -> None:
    """Dataset commands."""
    pass


@dataset.command("validate")
@click.argument("dataset_file", type=click.Path(exists=True))
def dataset_validate(dataset_file: str) -> None:
    """Validate a dataset file (task, episode, step, or snapshot)."""
    from agentversion.dataset import DatasetSnapshot, Episode, Step, Task

    kind_map: dict[str, type[BaseModel]] = {
        "task": Task,
        "episode": Episode,
        "step": Step,
        "dataset_snapshot": DatasetSnapshot,
    }

    with open(dataset_file) as f:
        data = json.load(f)

    kind = data.get("kind")
    if kind not in kind_map:
        console.print(f"[red]✗[/red] Unknown kind: {kind!r} (expected one of {list(kind_map.keys())})")
        raise SystemExit(1)

    try:
        model_cls = kind_map[kind]
        obj = model_cls.model_validate(data)
        console.print(f"[green]✓[/green] Valid {kind}: {getattr(obj, f'{kind}_id', 'ok')}")
    except Exception as e:
        console.print(f"[red]✗[/red] Invalid {kind}: {e}")
        raise SystemExit(1)

    if _print_id_issues(data, kind) > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
