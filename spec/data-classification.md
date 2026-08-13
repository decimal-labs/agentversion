# Data Classification

> Status: Stable v1.0 · Added in v0.9.0

Compliance labels on dataset snapshots — PII state, retention, residency, consent basis. Records the facts a compliance review needs, including the GDPR Article 6 legal basis, in a machine-readable form.

## Why

Production traces often contain PII (names, emails, payment info). Pre-v0.9, the spec had no place to record whether a snapshot's data was raw, redacted, or synthetic — so PII handling was an out-of-band Slack-thread affair, easy to break under audit.

`DatasetSnapshot.data_classification` gives compliance facts a typed home.

## Schema

```json
{
  "kind": "dataset_snapshot",
  "snapshot_id": "dss_01HZK1A2B3C4D5E6F7G8H9J0K1",
  ...
  "data_classification": {
    "pii_state":            "redacted",
    "retention_days":       90,
    "residency":            ["us-east-1", "eu-west-1"],
    "redaction_policy_ref": "redaction-policy:v3.1",
    "consent_basis":        "legitimate_interest"
  }
}
```

## Fields

| Field | Required | Description |
|---|---|---|
| `pii_state` | Default `"none"` | `raw` (contains unredacted PII), `redacted` (PII removed/masked per `redaction_policy_ref`), `synthetic` (generated, no real users), or `none` (never contained PII). |
| `retention_days` | Optional | How long the snapshot may be retained. Tools should enforce deletion or anonymization beyond this. |
| `residency` | Default `[]` | Allowed storage regions. Empty list = no constraint. |
| `redaction_policy_ref` | Optional | Reference to the policy used to produce a `redacted` state. Free-form string — typically a versioned policy ID. |
| `consent_basis` | Optional | GDPR Article 6 legal basis: `consent`, `contract`, `legitimate_interest`, `legal_obligation`, `vital_interest`, `public_task`. |

## Selection filter

`SelectionPolicy.pii_states` lets a downstream pipeline filter which episodes are eligible for a snapshot:

```json
"selection_policy": {
  "source_types": ["production", "replay"],
  "pii_states":   ["redacted", "synthetic", "none"]
}
```

This is the typical "build me an SFT set I can ship to a vendor" query. Episodes with `data_classification.pii_state == "raw"` get filtered out.

## Hash participation

Data classification is on the dataset snapshot itself (not on the agent manifest). It doesn't affect `identity.overall_hash` of any manifest, only the identity of the snapshot. Snapshots are hashed via the dataset spec's own rules (see [dataset.md](./dataset.md)).

## What this doesn't do

- **PII detection.** The spec assumes you classify out-of-band — a redaction pipeline labels the snapshot when it produces it. The spec doesn't ship a PII detector.
- **Per-row labels.** Classification is at the snapshot granularity. If individual episodes within a snapshot have different PII states, the snapshot must use the most permissive label, or be split.
- **Encryption-at-rest enforcement.** That's a platform concern. The spec only carries the labels needed to make policy decisions.
- **Verify the labels.** `pii_state` defaults to `none` and nothing verifies it, so a snapshot no pipeline ever classified will pass a `pii_states` filter. Label explicitly at production time and treat an absent classification as unknown.
