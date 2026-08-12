# Releasing agentversion

How to publish a new version of the `agentversion` package to PyPI.

> **PyPI is append-only.** A version number can never be reused, overwritten, or re-uploaded — even after you "delete" a release. If you ship a mistake, the only remedy is a *new* version. Treat the upload step as irreversible.

## One-time setup

1. A PyPI account with **2FA enabled** and maintainer rights on the `agentversion` project.
2. **[Trusted Publishing](https://docs.pypi.org/trusted-publishers/)** attached on the PyPI side, under PyPI → *Manage* → *Publishing*, matching exactly what `.github/workflows/publish.yml` declares: project `agentversion`, owner `decimal-labs`, repo `agentversion`, workflow `publish.yml`, environment `pypi`. With that in place the workflow authenticates over OIDC at publish time, so no long-lived credential has to exist anywhere.
3. Tooling: [`uv`](https://docs.astral.sh/uv/) installed. This is only needed for the local fallback below — the workflow path needs nothing installed on your machine.

## Versioning model

There are **two independent version numbers** — don't conflate them:

| Number | Lives in | Bump when |
|---|---|---|
| **Package version** | `pyproject.toml` `version` only | the Python reference implementation (models, diff, CLI) changes |
| **Spec version** (`SPEC_VERSION`) | `agentversion/constants.py` | the **wire format** changes — see the spec-evolution rules in `CONTRIBUTING.md`; **not** on a normal package release |

`agentversion/__init__.py` reads `__version__` back from installed metadata, so there is only **one** package-version string to edit (`pyproject.toml`). `SPEC_VERSION` is the contract other implementations target — leave it alone unless you are deliberately versioning the format (a much heavier process, gated by an ADR).

The package is pre-1.0 (`0.x`) while the API settles; the **spec** is frozen at `1.0.0`. It is normal and intended for these to differ.

## Cutting a release

1. **Pick the next package version** (SemVer).
2. **Bump it** in `pyproject.toml` → `version`. (Do **not** touch `SPEC_VERSION` unless you mean to.)
3. **Add a CHANGELOG entry**: `## [X.Y.Z] — YYYY-MM-DD` with the changes.
4. **If you touched the README**: make sure every link is an **absolute** `https://github.com/...` URL. Relative `./` links render broken on PyPI.
5. **Tag and publish a GitHub Release** named `vX.Y.Z` for the same version. That is the trigger for `.github/workflows/publish.yml`, which runs the test matrix on Python 3.10/3.11/3.12, builds the distributions, **fails the release if `pyproject.toml`'s version does not match the tag**, and uploads via Trusted Publishing.

   The `id-token: write` permission is granted to the publish job alone, never workflow-wide: the test job installs every transitive dev dependency and therefore runs third-party install-time code, which must not be able to mint a publishing credential.

## Local fallback

If you need to ship without the workflow, run the release script from the repo root:

```bash
./scripts/release.sh
```

It resolves the version, refuses to proceed if that version already exists on PyPI, builds, runs `twine check`, smoke-tests the built wheel — import + `__version__` + `SPEC_VERSION` + the `agentversion` CLI entry point — in a clean env, then **pauses for a typed `yes`** before the upload, and verifies afterward. It uploads with `twine`, so it needs PyPI credentials configured the way [twine documents](https://twine.readthedocs.io/en/stable/#configuration).

The raw equivalent, if you skip the script, gives up every one of those checks:

```bash
rm -rf dist && uv build
uvx twine check dist/*
uvx twine upload dist/*        # PERMANENT — cannot be undone
# verify (the version endpoint updates fastest; expect 200):
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/agentversion/<version>/json
```

## Notes & gotchas

- **Public repo, public package.** Every README badge, every `https://github.com/decimal-labs/agentversion/...` link and every cross-link to `skillevaluation` must resolve for a reader who has nothing checked out. A 404 is a real breakage to chase before you ship, not cosmetic — PyPI renders the README as-is and you cannot re-upload a fixed one under the same version.
- **Development Status** classifier in `pyproject.toml` is `4 - Beta`. Bump it as the package matures.
- **PyPI cache lag.** The top-level `https://pypi.org/pypi/agentversion/json` can stay cached on the previous version for a minute or two after upload; the version-specific `.../<version>/json` endpoint reflects new releases almost immediately.
- **The Trusted Publisher mapping is matched exactly.** Owner, repo, workflow filename and environment must all agree with what PyPI has on file; any difference — including a renamed workflow file — makes the upload step fail at the end of an otherwise green release run, after the tag already exists. Check the mapping before cutting the first release of a renamed or moved workflow.
