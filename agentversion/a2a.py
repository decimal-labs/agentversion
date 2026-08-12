"""Project an AgentVersion manifest onto an A2A (Agent2Agent) **Agent Card**.

A2A (the Agent2Agent protocol, now under the Linux Foundation) is the emerging interoperability standard
for how agents *advertise themselves* to other agents: an **Agent Card** is the public JSON descriptor
(name, capabilities, the skills it offers, I/O modes). AgentVersion is the complementary layer A2A does
NOT define: a **versioned, diffable, hashable contract** of what the agent actually IS internally, and a
breaking-change decision over your data. So the strategic position is "the version / diff / provenance
layer **on top of** A2A cards" — and this module is that seam.

``manifest_to_agent_card`` produces an Agent Card from a manifest, mapping the fields with a clean
correspondence and — crucially — stamping the manifest's identity (``manifest_id`` + ``overall_hash``)
onto the card under a namespaced extension, so a consumer can pin *which exact version* a card describes.
This is a deliberate PROJECTION (a card advertises a subset of the full contract), not a lossless dump;
the deployment ``url`` is supplied by the caller (it is not part of the internal contract).
"""

from __future__ import annotations

from typing import Any

from agentversion.manifest import AgentManifest

# The A2A protocol version this projection targets. Bump as the projection is validated against newer
# Agent Card schemas; kept explicit so the output is self-describing.
A2A_PROTOCOL_VERSION = "0.2.5"

_FORMAT_TO_MIME = {"json": "application/json", "text": "text/plain"}
_MODALITY_TO_MIME = {"image": "image/*", "audio": "audio/*", "video": "video/*", "text": "text/plain"}


def _capabilities(manifest: dict[str, Any]) -> dict[str, bool]:
    """A2A capabilities, read from the manifest's ``capabilities`` block when present (else conservative
    defaults). Accepts camelCase or snake_case keys from producers."""
    caps = manifest.get("capabilities") or {}

    def _flag(*names: str) -> bool:
        return any(bool(caps.get(n)) for n in names)

    return {
        "streaming": _flag("streaming"),
        "pushNotifications": _flag("pushNotifications", "push_notifications"),
        "stateTransitionHistory": _flag("stateTransitionHistory", "state_transition_history"),
    }


def _output_modes(contract: dict[str, Any]) -> list[str]:
    output = contract.get("output_contract") or {}
    modes: list[str] = []
    fmt = output.get("format")
    mime = _FORMAT_TO_MIME.get(fmt) if isinstance(fmt, str) else None
    if mime:
        modes.append(mime)
    for modality in output.get("modalities") or []:
        m = _MODALITY_TO_MIME.get(str(modality).lower())
        if m and m not in modes:
            modes.append(m)
    return modes or ["text/plain"]


def _skills(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """AgentVersion ``skill_registry`` entries → A2A skill descriptors (the capabilities the agent
    offers). Names map to ids; tags/description carried when present."""
    out: list[dict[str, Any]] = []
    for s in (contract.get("skill_registry") or {}).get("skills", []) or []:
        name = s.get("name") or ""
        out.append({
            "id": name,
            "name": name,
            "description": s.get("description") or "",
            "tags": list(s.get("tags") or []),
        })
    return out


def manifest_to_agent_card(
    manifest: dict[str, Any] | AgentManifest,
    *,
    url: str | None = None,
    protocol_version: str = A2A_PROTOCOL_VERSION,
) -> dict[str, Any]:
    """Project an AgentVersion manifest onto an A2A Agent Card dict.

    Args:
        manifest: a manifest dict or an ``AgentManifest``.
        url: the agent's A2A service endpoint (a deployment concern not in the internal contract). Added
            to the card only when supplied.
        protocol_version: the A2A ``protocolVersion`` to stamp.

    Returns:
        An Agent Card dict. Beyond the standard fields it carries an ``x-agentversion`` provenance block
        (manifest_id + overall_hash + spec_version) so a card consumer can pin the exact version — the
        capability A2A itself does not provide.
    """
    m = manifest.model_dump(mode="json") if isinstance(manifest, AgentManifest) else manifest
    contract = m.get("contract") or {}

    card: dict[str, Any] = {
        "protocolVersion": protocol_version,
        "name": m.get("agent_name"),
        "description": m.get("description") or "",
        "version": m.get("version_label") or "",
        "capabilities": _capabilities(m),
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": _output_modes(contract),
        "skills": _skills(contract),
    }
    if url is not None:
        card["url"] = url

    created_by = m.get("created_by") or {}
    org = created_by.get("organization") or created_by.get("name")
    if org:
        card["provider"] = {"organization": org}

    # Provenance — the differentiation. A2A Agent Cards permit additional fields; namespace ours so a
    # consumer can resolve EXACTLY which versioned manifest this card was projected from.
    identity = m.get("identity") or {}
    card["x-agentversion"] = {
        "manifest_id": m.get("manifest_id"),
        "overall_hash": identity.get("overall_hash"),
        "spec_version": m.get("spec_version"),
    }
    return card
