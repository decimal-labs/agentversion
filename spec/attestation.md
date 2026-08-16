# Attestation

> Status: Stable v1.0 · Added in v0.9.0

Cryptographic signatures over a manifest's canonical hash. Turns `created_by` from a *claim* into an *assertion*.

## Why

Pre-v0.9, `created_by: {"type": "user", "id": "stanley"}` was a free-text field. Anyone editing the JSON could write any string there — there was no way to verify that a manifest actually came from the pipeline it claims.

Attestations fix that. Each entry in `identity.attestations[]` is a signature over `identity.overall_hash`, produced by a signer (typically a CI pipeline via Sigstore, an org-controlled key, or a cosign/in-toto provenance attestation).

## Schema

```json
{
  "identity": {
    "overall_hash": "sha256:47301b25…",
    "attestations": [
      {
        "signer":              "sigstore:github.com/decimal-labs/agentversion@.github/workflows/release.yml",
        "algorithm":           "cosign-rsa-sha256",
        "signature":           "MEUCIQDx9k…",
        "signed_payload_hash": "sha256:47301b25…",
        "signed_at":           "2026-05-15T10:00:00Z",
        "key_id":              "abc123",
        "expires_at":          "2027-05-15T10:00:00Z"
      }
    ]
  }
}
```

Multiple attestations are allowed — common cases:
- One from CI (proves provenance)
- One from a release manager (proves human approval)
- One from a security review pipeline (proves the manifest passed scans)

## Fields

| Field | Required | Description |
|---|---|---|
| `signer` | Yes | Identifier of the signer. Convention: `sigstore:<issuer>@<workflow>`, `keyring:<key-name>`, or `x509:<subject>`. |
| `algorithm` | Yes | Signature algorithm. Examples: `cosign-rsa-sha256`, `ssh-ed25519`, `x509-rsa-pss-sha256`. |
| `signature` | Yes | Base64-encoded signature bytes. |
| `signed_payload_hash` | Yes | The hash that was signed. Must equal `identity.overall_hash`; the validator enforces this (error code `attestation_payload_mismatch`). Cryptographic signature verification remains delegated to implementations, since it requires the public key. |
| `signed_at` | Yes | When the signature was produced. |
| `key_id` | Optional | Hint for key resolution. |
| `expires_at` | Optional | When the signature should be considered stale (independent of key revocation). |

## Verification (out of scope for the spec)

The spec defines the *format* of attestations. **Verification is delegated to implementations** for two reasons:

1. Different organizations use different trust roots (Sigstore vs internal PKI vs cosign keyless).
2. The spec shouldn't bundle a crypto stack.

A conforming implementation may verify attestations or not — but if it does, it should:

- Confirm `signed_payload_hash == identity.overall_hash`.
- Resolve `key_id` (if present) and verify `signature` against the canonical hash bytes using `algorithm`.
- Refuse verification if `expires_at` is in the past.
- Refuse verification if the signer's key has been revoked.

A future spec extension may define a `verify` CLI command that delegates to a pluggable backend (Sigstore, cosign, GPG).

## Hash participation

**Attestations are NOT part of `contract`** — they live in `identity`, which is excluded from `overall_hash` by design. Adding or rotating attestations on a manifest **does not** change its hash.

This is intentional: a manifest's identity is its contract content, not its signatures. Anyone holding a copy of the manifest can verify the signature against the hash they compute themselves.

## Yank + attestation

A yanked manifest (`identity.yanked_at` set; see §3j) retains its attestations. Tools that distrust yanked manifests should refuse to honor them regardless of valid signatures — yanking is the org's stronger statement.
