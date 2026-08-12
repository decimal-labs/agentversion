"""Semantic validator for AgentVersion.

Goes beyond JSON Schema structural validation to enforce business rules
defined in spec/reference.md §13.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agentversion.hasher import hash_manifest, hash_surface
from agentversion.ids import check_object_ids
from agentversion.manifest import AgentManifest
from agentversion.refs import try_parse_manifest_ref

# §3i tool semantic_version pattern: MAJOR.MINOR.PATCH (+ optional pre-release / build).
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?$")

# §3e: which lifecycle.current_stage values each simple status field may pair with.
_SIMPLE_TO_LIFECYCLE: dict[str, set[str]] = {
    "draft":      {"draft"},
    "active":     {"candidate", "staging", "production"},
    "deprecated": {"deprecated"},
    "archived":   {"archived"},
}


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: Severity
    code: str
    message: str
    path: str | None = None


@dataclass
class ValidationResult:
    """Result of validating a manifest."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    manifest: AgentManifest | None = None

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]


def _load_manifest_schema() -> dict[str, Any] | None:
    """Locate and load the bundled ``agent-manifest.schema.json``.

    Works both from a source checkout (``<repo>/schemas/``) and an installed
    wheel (the schemas are force-included under ``agentversion/schemas/``).
    Returns ``None`` if the schema can't be found.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here / "schemas", here.parent / "schemas"):
        path = candidate / "agent-manifest.schema.json"
        if path.is_file():
            schema: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return schema
    return None


def validate_manifest(
    data: dict[str, Any],
    *,
    check_hash: bool = True,
    check_schema: bool = False,
) -> ValidationResult:
    """Validate a manifest dict against Pydantic models and semantic rules.

    Args:
        data: The manifest as a dict (e.g. parsed from JSON).
        check_hash: If True, verify that ``identity.overall_hash`` matches
            the computed hash from the contract block.
        check_schema: If True, additionally validate the raw dict against the
            bundled ``agent-manifest.schema.json`` and report any structural
            violations (e.g. unknown top-level keys the Pydantic models would
            silently drop) as WARNING issues. Opt-in because it requires the
            ``jsonschema`` package and is stricter than the Pydantic models.

    Returns:
        A ``ValidationResult`` with the parsed manifest (if structurally valid)
        and any issues found.
    """
    issues: list[ValidationIssue] = []
    manifest: AgentManifest | None = None

    # --- 1. Structural validation via Pydantic ---
    try:
        manifest = AgentManifest.model_validate(data)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"])
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="pydantic_validation",
                    message=err["msg"],
                    path=loc,
                )
            )
        return ValidationResult(valid=False, issues=issues)

    # --- 1b. Optional JSON Schema structural validation (opt-in) ---
    if check_schema:
        try:
            import jsonschema
        except ImportError:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="schema_check_unavailable",
                    message="check_schema=True but the 'jsonschema' package is not installed",
                )
            )
        else:
            schema = _load_manifest_schema()
            if schema is None:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="schema_check_unavailable",
                        message="check_schema=True but agent-manifest.schema.json could not be located",
                    )
                )
            else:
                checker = jsonschema.Draft202012Validator(schema)
                for err in sorted(checker.iter_errors(data), key=lambda e: list(e.absolute_path)):
                    loc = ".".join(str(p) for p in err.absolute_path)
                    issues.append(
                        ValidationIssue(
                            severity=Severity.WARNING,
                            code="schema_violation",
                            message=err.message,
                            path=loc or None,
                        )
                    )

    # --- 2. Semantic rules (§13) ---

    # Rule: parent_manifest_id != manifest_id
    if manifest.parent_manifest_id and manifest.parent_manifest_id == manifest.manifest_id:
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                code="self_referencing_parent",
                message="parent_manifest_id must not equal manifest_id",
                path="parent_manifest_id",
            )
        )

    # Rule: ID format (delegated to ids.check_object_ids).
    for sev, code, message, path in check_object_ids(data, kind="agent_manifest"):
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR if sev == "error" else Severity.WARNING,
                code=code,
                message=message,
                path=path,
            )
        )

    # Rule: subagent manifest_ref must parse as a typed URI.
    for i, sa in enumerate(manifest.contract.subagents or []):
        if sa.manifest_ref is None:
            continue
        path = f"contract.subagents[{i}].manifest_ref"
        if try_parse_manifest_ref(sa.manifest_ref) is None:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="malformed_manifest_ref",
                    message=(
                        f"{path}={sa.manifest_ref!r} doesn't match any recognized form. "
                        f"Use 'agentversion:manifest:<id>', 'agentversion:hash:<algo>:<hex>', "
                        f"'https://...', or 'file://...'."
                    ),
                    path=path,
                )
            )

    # Rule: lifecycle consistency (§3e)
    if manifest.lifecycle is not None:
        lc = manifest.lifecycle
        if lc.history:
            # History must be sorted by transitioned_at (oldest first). Pydantic accepts both
            # tz-aware and naive datetimes; comparing a mixed list raises TypeError, so normalize
            # naive values to UTC for the sort-order check (this comparison only — it does not
            # mutate the manifest).
            def _sort_key(dt: datetime) -> datetime:
                return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

            ts = [h.transitioned_at for h in lc.history]
            if [_sort_key(t) for t in ts] != sorted(ts, key=_sort_key):
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="lifecycle_history_unsorted",
                        message="lifecycle.history entries must be sorted by transitioned_at (oldest first)",
                        path="lifecycle.history",
                    )
                )
            # current_stage must match the last history entry
            if lc.history[-1].stage != lc.current_stage:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="lifecycle_stage_mismatch",
                        message=(
                            f"lifecycle.current_stage={lc.current_stage!r} but "
                            f"lifecycle.history[-1].stage={lc.history[-1].stage!r}"
                        ),
                        path="lifecycle.current_stage",
                    )
                )
        # Cross-check status (the simple field) against lifecycle.current_stage
        if manifest.status is not None:
            allowed = _SIMPLE_TO_LIFECYCLE.get(manifest.status, set())
            if lc.current_stage not in allowed:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="lifecycle_status_mismatch",
                        message=(
                            f"status={manifest.status!r} doesn't agree with "
                            f"lifecycle.current_stage={lc.current_stage!r} "
                            f"(expected one of {sorted(allowed)})"
                        ),
                        path="status",
                    )
                )

    # Rule: evaluation gates internal consistency (§3k)
    if manifest.evaluation is not None:
        for i, gate in enumerate(manifest.evaluation.gates):
            if gate.threshold_direction == "min":
                expected_pass = gate.actual_score >= gate.threshold
            else:  # "max"
                expected_pass = gate.actual_score <= gate.threshold
            if gate.passed != expected_pass:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="eval_gate_inconsistent",
                        message=(
                            f"gate {gate.name!r}: passed={gate.passed} but "
                            f"actual_score={gate.actual_score} vs threshold={gate.threshold} "
                            f"(direction={gate.threshold_direction}) implies passed={expected_pass}"
                        ),
                        path=f"evaluation.gates[{i}].passed",
                    )
                )

    # Rule: tool hashes should be unique within registry
    tool_hashes: dict[str, str] = {}
    for tool in manifest.contract.tool_registry.tools:
        if tool.hash in tool_hashes:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="duplicate_tool_hash",
                    message=(
                        f"Tool '{tool.name}' has the same hash as "
                        f"tool '{tool_hashes[tool.hash]}'"
                    ),
                    path=f"contract.tool_registry.tools[{tool.name}]",
                )
            )
        else:
            tool_hashes[tool.hash] = tool.name

    # Rule: tool inline schema must match its hash (§3g)
    for i, tool in enumerate(manifest.contract.tool_registry.tools):
        for kind in ("input", "output"):
            inline = getattr(tool, f"{kind}_schema_inline")
            declared_hash = getattr(tool, f"{kind}_schema_hash")
            if inline is None:
                continue
            actual_hash = hash_surface(inline)
            if declared_hash is not None and declared_hash != actual_hash:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        code="schema_hash_mismatch",
                        message=(
                            f"tool {tool.name!r} {kind}_schema_inline hashes to "
                            f"{actual_hash} but {kind}_schema_hash declares {declared_hash}"
                        ),
                        path=f"contract.tool_registry.tools[{i}].{kind}_schema_inline",
                    )
                )

    # Rule: tool semantic_version validity (§3i)
    for i, tool in enumerate(manifest.contract.tool_registry.tools):
        if tool.semantic_version is None:
            continue
        if not _SEMVER_RE.match(tool.semantic_version):
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="malformed_semver",
                    message=(
                        f"tool {tool.name!r} semantic_version={tool.semantic_version!r} "
                        f"is not a valid semver string (MAJOR.MINOR.PATCH)"
                    ),
                    path=f"contract.tool_registry.tools[{i}].semantic_version",
                )
            )

    # Rule: hash_algorithm should be the standard jcs-sha256
    if manifest.identity.hash_algorithm != "jcs-sha256":
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                code="unsupported_hash_algorithm",
                message=(
                    f"hash_algorithm '{manifest.identity.hash_algorithm}' is not "
                    f"the standard 'jcs-sha256'"
                ),
                path="identity.hash_algorithm",
            )
        )

    # Rule: an attestation must actually cover THIS manifest (§3d integrity linkage).
    # We do NOT verify the signature cryptographically — that is delegated to a verifier with a key /
    # trust store (see Attestation docstring). But the cheap, no-crypto linkage MUST hold: the
    # `signed_payload_hash` is "the canonical-hash value that was signed", so it must equal the
    # manifest's declared `overall_hash`. A mismatch means the attestation provably signs a DIFFERENT
    # artifact (copy-pasted / tampered envelope) — without this check it was inert and a manifest could
    # carry an attestation for any other payload and still validate.
    for i, att in enumerate(manifest.identity.attestations or []):
        if att.signed_payload_hash != manifest.identity.overall_hash:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="attestation_payload_mismatch",
                    message=(
                        f"attestation[{i}] signs payload hash {att.signed_payload_hash!r} but the "
                        f"manifest's overall_hash is {manifest.identity.overall_hash!r} — the "
                        f"attestation does not cover this manifest (cryptographic signature "
                        f"verification is delegated to a verifier and not performed here)"
                    ),
                    path=f"identity.attestations[{i}].signed_payload_hash",
                )
            )

    # Rule: overall_hash should be reproducible
    if check_hash:
        try:
            computed = hash_manifest(data)
            if manifest.identity.overall_hash != computed:
                issues.append(
                    ValidationIssue(
                        severity=Severity.WARNING,
                        code="hash_mismatch",
                        message=(
                            f"Declared overall_hash '{manifest.identity.overall_hash}' "
                            f"does not match computed hash '{computed}'"
                        ),
                        path="identity.overall_hash",
                    )
                )
        except (ValueError, TypeError) as e:
            # The hasher raises ValueError on data it refuses to canonicalize
            # (e.g. a non-finite float — see spec/hashing.md). That is a malformed
            # manifest whose identity can never be reproduced, so it's an ERROR,
            # not a soft warning that still validates.
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="hash_uncomputable",
                    message=f"Contract cannot be canonically hashed: {e}",
                    path="identity.overall_hash",
                )
            )
        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    code="hash_computation_failed",
                    message=f"Could not compute hash for verification: {e}",
                    path="identity.overall_hash",
                )
            )

    has_errors = any(i.severity == Severity.ERROR for i in issues)
    return ValidationResult(valid=not has_errors, issues=issues, manifest=manifest)


def validate_manifest_file(
    path: str | Path,
    *,
    check_hash: bool = True,
    check_schema: bool = False,
) -> ValidationResult:
    """Convenience: load a JSON file and validate it.

    Args:
        path: Path to a JSON manifest file.
        check_hash: Forwarded to :func:`validate_manifest`.
        check_schema: Forwarded to :func:`validate_manifest`.

    Returns:
        A ``ValidationResult``.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="json_parse_error",
                    message=f"Invalid JSON: {e}",
                )
            ],
        )
    except FileNotFoundError:
        return ValidationResult(
            valid=False,
            issues=[
                ValidationIssue(
                    severity=Severity.ERROR,
                    code="file_not_found",
                    message=f"File not found: {path}",
                )
            ],
        )
    return validate_manifest(data, check_hash=check_hash, check_schema=check_schema)
