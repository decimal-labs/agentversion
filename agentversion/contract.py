"""Assemble an agentversion contract block from a flat component list.

The single source of truth for how a producer's *flat* components (one entry per
tool / prompt / model / …) regroup into the contract-keyed surfaces the diff and
the identity hash are computed from. The DecimalAI platform calls this directly;
the DecimalAI SDK exporter (``ManifestSnapshot.to_agentversion``) mirrors it and
is held byte-identical to it by a cross-implementation test — so a producer and a
consumer compute the *same* ``jcs-sha256`` identity hash for the same agent.

Each component is a plain dict::

    {
      "component_type":    "tool" | "skill" | "prompt" | "model" | "subagent"
                           | "output_schema" | "workflow" | "guardrail"
                           | "context_config" | "behavioral_policy"
                           | "environment",
      "component_name":    str,
      "component_version": str | None,
      "content_hash":      str | None,   # producer-supplied content fingerprint
      "schema_json":       dict | None,  # per-type detail (see the producer)
    }
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentversion.diff import surface_key_for_component

__all__ = ["contract_from_components", "quantize_float"]


def quantize_float(value: float | None, step: float = 0.1) -> float | None:
    """Quantize a float to the nearest ``step`` (0.71 → 0.7) for stable hashing.

    Returns ``None`` for ``None``. Rounds to 10 decimals to shed IEEE-754 noise
    (e.g. ``0.7000000000000001``). Must match the producer's quantization so the
    exported ``generation_config`` agrees with the hashed ``model_config_hash``.
    """
    if value is None:
        return None
    return round(round(value / step) * step, 10)


def _infer_provider(model_name: str | None) -> str:
    """Best-effort provider inference from a model id (when none is declared)."""
    name = (model_name or "").lower()
    if "gemini" in name or "google" in name:
        return "google"
    if "gpt" in name or "openai" in name or name.startswith(("o1", "o3", "o4")):
        return "openai"
    if "claude" in name or "anthropic" in name:
        return "anthropic"
    return "unknown"


def _hash_content(content: Any) -> str:
    """SHA-256 of JSON-serialized content (bare hex digest, no ``sha256:`` prefix)."""
    serialized = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _compute_surface_hash(surface_name: str, components: list[dict[str, Any]]) -> str:
    """Deterministic hash for one contract surface (matches the SDK's surface hash).

    A version-only bump still changes the hash because ``version`` is part of each
    per-component record.
    """
    surface_comps = sorted(
        [c for c in components if surface_key_for_component(c.get("component_type", "")) == surface_name],
        key=lambda c: c.get("component_name") or "",
    )
    if not surface_comps:
        return ""
    data = [
        {
            "name": c.get("component_name"),
            "hash": c.get("content_hash"),
            "version": c.get("component_version"),
        }
        for c in surface_comps
    ]
    return _hash_content(data)


def contract_from_components(components: list[dict[str, Any]]) -> dict[str, Any]:
    """Regroup a flat component list into the contract-keyed surface block.

    The returned dict is the ``contract`` value of an agentversion manifest — the
    block the diff engine and ``hash_manifest`` operate on. Required surfaces
    (prompt_stack, model_runtime, tool_registry, workflow, output_contract) are
    always present; optional surfaces only when the components declare them.
    """
    by_type: dict[str, list[dict[str, Any]]] = {}
    for c in components:
        by_type.setdefault(c.get("component_type", ""), []).append(c)

    def _ref(c: dict[str, Any]) -> dict[str, str]:
        return {
            "id": c.get("component_name", ""),
            "version": c.get("component_version") or "1",
            "hash": c.get("content_hash") or "",
        }

    # prompt_stack — two ref slots (system / developer). Named prompts claim their
    # slot; anything left fills open slots in order.
    prompt_stack: dict[str, Any] = {}
    leftover: list[dict[str, Any]] = []
    for c in by_type.get("prompt", []):
        key = (c.get("component_name") or "").lower()
        if key in ("system", "system_prompt"):
            prompt_stack.setdefault("system_prompt", _ref(c))
        elif key in ("developer", "developer_prompt", "instruction", "instructions"):
            prompt_stack.setdefault("developer_prompt", _ref(c))
        else:
            leftover.append(c)
    for c in leftover:
        if "system_prompt" not in prompt_stack:
            prompt_stack["system_prompt"] = _ref(c)
        elif "developer_prompt" not in prompt_stack:
            prompt_stack["developer_prompt"] = _ref(c)

    # model_runtime (required: provider + model).
    model_comps = sorted(by_type.get("model", []), key=lambda c: c.get("component_name") or "")
    if model_comps:
        primary = model_comps[0]
        cfg = primary.get("schema_json") or {}
        model = cfg.get("model") or primary.get("component_version") or "unknown"
        provider = cfg.get("provider") or _infer_provider(
            cfg.get("model") or primary.get("component_version") or primary.get("component_name")
        )
        model_runtime: dict[str, Any] = {"provider": provider, "model": model}
        if primary.get("content_hash"):
            model_runtime["model_config_hash"] = primary["content_hash"]
        # Export the QUANTIZED temperature/top_p (the same steps used for the
        # model_config_hash) so the exported config agrees with the hash.
        gen: dict[str, Any] = {}
        if isinstance(cfg.get("temperature"), (int, float)):
            gen["temperature"] = quantize_float(cfg["temperature"], 0.1)
        if isinstance(cfg.get("top_p"), (int, float)):
            gen["top_p"] = quantize_float(cfg["top_p"], 0.05)
        if isinstance(cfg.get("max_tokens"), int):
            gen["max_tokens"] = cfg["max_tokens"]
        if isinstance(cfg.get("response_format"), str):
            gen["response_format"] = cfg["response_format"]
        if gen:
            model_runtime["generation_config"] = gen
        # tool_calling_mode + runtime_version are TOP-LEVEL model_runtime fields
        # (not under generation_config); the diff classifies a tool_calling_mode
        # change as breaking. Must stay byte-identical with the SDK exporter.
        if isinstance(cfg.get("tool_calling_mode"), str):
            model_runtime["tool_calling_mode"] = cfg["tool_calling_mode"]
        if isinstance(cfg.get("runtime_version"), str):
            model_runtime["runtime_version"] = cfg["runtime_version"]
    else:
        model_runtime = {"provider": "unknown", "model": "unknown"}

    # tool_registry (required).
    tools_out: list[dict[str, Any]] = []
    for c in by_type.get("tool", []):
        sj = c.get("schema_json") or {}
        td: dict[str, Any] = {"name": c.get("component_name", ""), "hash": c.get("content_hash") or ""}
        if c.get("component_version"):
            td["version"] = c["component_version"]
        if sj.get("description"):
            td["description"] = sj["description"]
        if sj.get("input_schema_hash"):
            td["input_schema_hash"] = sj["input_schema_hash"]
        if sj.get("output_schema_hash"):
            td["output_schema_hash"] = sj["output_schema_hash"]
        if sj.get("stability") in ("experimental", "stable", "deprecated"):
            td["stability"] = sj["stability"]
        if isinstance(sj.get("annotations"), dict):
            td["annotations"] = sj["annotations"]
        tools_out.append(td)
    tool_registry = {
        "registry_version": "1",
        "registry_hash": _compute_surface_hash("tool_registry", components),
        "tools": tools_out,
    }

    # workflow (required surface; all fields optional → {} is valid).
    workflow: dict[str, Any] = {}
    wf_comps = by_type.get("workflow", [])
    if wf_comps:
        wf = wf_comps[0]
        workflow["graph_name"] = wf.get("component_name", "")
        if wf.get("component_version"):
            workflow["graph_version"] = wf["component_version"]
        if wf.get("content_hash"):
            workflow["graph_hash"] = wf["content_hash"]

    # output_contract (required: version + schema_hash + format).
    out_comps = by_type.get("output_schema", [])
    if out_comps:
        oc = out_comps[0]
        sj = oc.get("schema_json") or {}
        fmt = sj.get("format")
        output_contract = {
            "version": oc.get("component_version") or "1",
            "schema_hash": oc.get("content_hash") or "",
            "format": fmt if isinstance(fmt, str) else "json",
            "strict": bool(sj.get("strict", False)),
            "modalities": sj["modalities"] if isinstance(sj.get("modalities"), list) else [],
        }
    else:
        output_contract = {
            "version": "0", "schema_hash": "", "format": "none",
            "strict": False, "modalities": [],
        }

    contract: dict[str, Any] = {
        "prompt_stack": prompt_stack,
        "model_runtime": model_runtime,
        "tool_registry": tool_registry,
        "workflow": workflow,
        "output_contract": output_contract,
    }

    # Optional surfaces — only when declared.
    skill_comps = by_type.get("skill", [])
    if skill_comps:
        skills_out: list[dict[str, Any]] = []
        for c in skill_comps:
            sj = c.get("schema_json") or {}
            sd: dict[str, Any] = {"name": c.get("component_name", ""), "hash": c.get("content_hash") or ""}
            if c.get("component_version"):
                sd["version"] = c["component_version"]
            if sj.get("description"):
                sd["description"] = sj["description"]
            if sj.get("stability") in ("experimental", "stable", "deprecated"):
                sd["stability"] = sj["stability"]
            skills_out.append(sd)
        contract["skill_registry"] = {
            "registry_version": "1",
            "registry_hash": _compute_surface_hash("skill_registry", components),
            "skills": skills_out,
        }

    subagents_out = [
        {"name": c.get("component_name", ""), "version": c.get("component_version") or "1",
         "hash": c.get("content_hash") or ""}
        for c in by_type.get("subagent", [])
    ]
    if subagents_out:
        contract["subagents"] = subagents_out

    if by_type.get("guardrail"):
        contract["guardrails"] = {
            "bundle_version": "1",
            "bundle_hash": _compute_surface_hash("guardrails", components),
        }

    ctx_comps = by_type.get("context_config", [])
    if ctx_comps:
        ctx = {"retrieval_config_version": "1"}
        if ctx_comps[0].get("content_hash"):
            ctx["retrieval_config_hash"] = ctx_comps[0]["content_hash"]
        contract["context_config"] = ctx

    # behavioral_policy / environment are single structured surfaces (the surface
    # IS the config), emitted verbatim from schema_json so hash_manifest hashes
    # their contents. Must stay byte-identical with the SDK exporter.
    bp_comps = by_type.get("behavioral_policy", [])
    if bp_comps:
        contract["behavioral_policy"] = dict(bp_comps[0].get("schema_json") or {})

    env_comps = by_type.get("environment", [])
    if env_comps:
        contract["environment"] = dict(env_comps[0].get("schema_json") or {})

    return contract
