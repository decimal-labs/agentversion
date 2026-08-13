# Security Policy

This repository holds two things: the AgentVersion **specification** (`spec/`, `schemas/`,
`compatibility-tests/`) and its **reference implementation** (the `agentversion` Python package,
published on [PyPI](https://pypi.org/project/agentversion/)). Both are in scope, and it is worth
saying which one you think you found a problem in — the fix is very different.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Two ways to reach us, either is fine:

- **GitHub private vulnerability reporting** — **Security → Report a vulnerability** on this
  repository. That keeps the report private to the maintainers and keeps the exchange attached to
  the code.
- **Email** — [hello@decimal.ai](mailto:hello@decimal.ai). A PGP key is available on request if you
  would rather not send details in cleartext.

Include what you have: what you found, how to reproduce it, the package version or `spec_version`
you were on, and what an attacker could actually do with it. A rough proof-of-concept — a manifest
pair, a fixture, a failing test — is worth more than a careful description.

## Scope

**A flaw in the specification** is one where an implementation that follows `spec/` correctly still
ends up unsafe. Those are the ones we most want to hear about, because every conforming
implementation inherits them. Examples:

- Canonicalization or hashing ambiguity — two materially different manifests that produce the same
  `overall_hash`, or one manifest that hashes differently under two defensible readings of
  `spec/hashing.md`.
- A compatibility rule in `spec/compatibility-policy.md` that classifies a genuinely breaking
  surface change as `non_breaking`, so downstream data is silently kept when it should be dropped.
- An attestation or replay-determinism claim (`spec/attestation.md`, `spec/replay-determinism.md`)
  that can be satisfied without the property it is meant to prove.
- Guidance in `spec/data-classification.md` that leads implementers to put secrets or unredacted
  personal data into a manifest field that is designed to be shared or published.

**A flaw in the reference implementation** is one where the Python package misbehaves regardless of
what the spec says. In scope:

- Anything in `agentversion/`, `scripts/`, and the wheel and sdist published as `agentversion` on
  PyPI — including a published artifact that does not match this source tree.
- Unsafe handling of untrusted input. The CLI and library read manifest JSON written by other
  people: parser crashes, unbounded resource use, path traversal on file arguments, or schema
  validation that can be bypassed all count.
- Any code path that logs, prints, or writes to disk a value the manifest marked as sensitive.

**Out of scope**

- The DecimalAI hosted platform (`api.decimal.ai`, `app.decimal.ai`). Report those the same way, to
  the same address — they are just not this repository, and the fix lands elsewhere.
- Design decisions documented in `spec/` and the ADRs under `adrs/` that you disagree with but that
  have no exploitable consequence. Those are worth an issue or an ADR, not a security report.
- Vulnerabilities in dependencies, unless this package's use of them is what makes them reachable.
- Scanner output with no demonstrated impact.

## What happens next

We are a small team with no on-call rotation, so rather than promise a response time or a formal
process we cannot hold to, here is what we actually do:

- We acknowledge a report once we have read it, and we say plainly if triage is going to take a
  while.
- We tell you whether we consider it in scope and what we intend to do.
- Fixes ship in an ordinary release and are described in `CHANGELOG.md`. We do not run a published
  advisory or CVE process, so please don't wait on one — if you intend to write up what you found,
  tell us and we will work out the timing together rather than impose a deadline on you.
- We are happy to credit you in the `CHANGELOG.md` entry and — for a spec fix — the ADR. Tell us how
  you want to be named, or say you would rather not be.

There is no paid bug bounty. That is a resourcing decision, not a judgment about the value of your
work.

## Safe harbour

If you make a good-faith effort to follow this policy, we will not pursue or support legal action
against you for your research. Good faith means avoiding privacy violations and service degradation,
only interacting with accounts and data you own or have permission to test, and giving us a
reasonable opportunity to fix the issue before you disclose it publicly.

If you are not sure whether what you found is a security issue, email
[hello@decimal.ai](mailto:hello@decimal.ai) and ask. That is always the right call.
