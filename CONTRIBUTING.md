# Contributing to AgentVersion

Thanks for your interest. AgentVersion is intended to be a stable, infrastructure-grade specification, so changes follow a slower and more deliberate process than typical libraries.

## How to propose a change

1. **Open an issue first** describing the problem. Don't open a PR before there's agreement that the change is desirable — spec evolution requires consensus.
2. **For non-trivial changes, write an ADR** under `adrs/NNNN-<slug>.md` using `adrs/0000-template.md`. ADRs capture the *why*. The spec docs in `spec/` capture the *what*.
3. **Reference the ADR from the PR.** ADRs may be amended or superseded but never deleted; they are the design log.

## Spec evolution rules

The `spec_version` follows [Semantic Versioning 2.0.0](https://semver.org/). The wire spec is at 1.0.0 and stable, so the rules below apply in full. (The Python package version is separate and still pre-1.0 — see the README.)

**Allowed in a minor bump (1.x.0):**

- Adding new optional fields to any object
- Adding new values to enums (`step_type`, `reason_code`, `decision` verbs, etc.)
- Adding new `kind` values (introducing new spec objects)
- Adding new `$defs` to JSON Schemas

**Requires a major bump (x.0.0):**

- Removing or renaming any field
- Making an optional field required
- Changing field types or value semantics
- Changing the canonical hashing algorithm
- Removing enum values
- Changing the `overall_hash` derivation

When you propose a breaking change, your PR must include:

- The ADR explaining the motivation
- An entry in `CHANGELOG.md` under the next major version
- A migration note in `spec/versioning-policy.md`
- Updates to the conformance fixtures (`compatibility-tests/`) so existing implementations can verify their migrations

## Code conventions

- Python ≥ 3.10, strict typing (`mypy --strict`).
- Pydantic v2 models are the source of truth for serialization; JSON Schemas mirror them.
- Tests live under `tests/`. Conformance fixtures live under `compatibility-tests/`.
- One canonical example per concept under `examples/`. Recompute hashes (`agentversion hash <file>`) whenever you change a manifest's `contract` block.

## What to test

Every PR should run:

```bash
pip install -e ".[dev]"
pytest                     # full suite, including conformance scenarios
ruff check .
mypy agentversion
```

Run them locally and read the output. CI runs the same four commands; they are defined in `.github/workflows/ci.yml`.

The conformance scenarios (`tests/test_conformance.py`) are non-negotiable. If your change breaks them, either the scenario is stale (update it) or your change breaks compatibility (then it's a major bump, not a minor).

## Releases

The maintainer cuts releases — see [`RELEASING.md`](./RELEASING.md) for the full runbook.

Today releases are published manually with `./scripts/release.sh` (local build + `twine` upload to PyPI). The release-triggered CI path via [trusted publishing](https://docs.pypi.org/trusted-publishers/) — no token stored — is already written as `.github/workflows/publish.yml`; it takes over once the publisher is attached on PyPI. See [`RELEASING.md`](./RELEASING.md).

## License

By contributing, you agree your contribution is licensed under [Apache 2.0](./LICENSE), the same as the project.
