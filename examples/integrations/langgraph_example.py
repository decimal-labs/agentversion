"""LangGraph integration example — build an Agent Manifest from a graph.

Shows how to generate a manifest from a LangGraph agent by inspecting the graph
structure, tools, and model configuration. Surface contents are fingerprinted with
``hash_surface`` (the real canonical hash), and ``compute_and_set_hashes`` fills in
the per-surface and ``identity.overall_hash`` values — so the result is a genuine,
validating manifest, not a placeholder shape.

This is a reference example; adapt the extraction to your actual LangGraph setup.

Run it (no LangGraph needed — it builds a representative manifest and validates it)::

    python langgraph_example.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from agentversion.hasher import compute_and_set_hashes, hash_surface
from agentversion.ids import mint_id
from agentversion.validator import validate_manifest


def extract_manifest_from_langgraph(
    graph: Any,
    *,
    agent_name: str = "my-agent",
    version_label: str = "v1",
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract an Agent Manifest from a compiled LangGraph StateGraph.

    Inspects the graph to populate:
    - nodes / edges → ``workflow`` topology (hashed into ``graph_hash``)
    - bound tools → ``tool_registry`` (each tool fingerprinted via ``hash_surface``)
    - ``model`` arg → ``model_runtime``

    Args:
        graph: A compiled LangGraph StateGraph.
        agent_name: Name for the agent.
        version_label: Version label for this deployment.
        model: ``{"provider": ..., "model": ...}`` for the runtime (optional).

    Returns:
        A manifest dict with all hashes computed — ready to ``validate``/``diff``.
    """
    # --- Extract graph topology (LangGraph exposes .nodes / .edges after compile) ---
    nodes = list(getattr(graph, "nodes", {}).keys())
    edges: list[list[str]] = []
    for src, targets in getattr(graph, "edges", {}).items():
        if isinstance(targets, dict):
            edges.extend([src, tgt] for tgt in targets.values())
        elif isinstance(targets, str):
            edges.append([src, targets])

    # --- Extract tools, fingerprinting each by its actual descriptor ---
    tools = []
    for _node_name, node in getattr(graph, "nodes", {}).items():
        for tool in getattr(node, "tools", None) or []:
            tool_name = getattr(tool, "name", str(tool))
            descriptor = {
                "name": tool_name,
                "description": getattr(tool, "description", None),
                "args_schema": str(getattr(tool, "args_schema", None)),
            }
            tools.append({
                "name": tool_name,
                "version": "1",
                "hash": hash_surface(descriptor),  # real content hash, not a placeholder
                "stability": "stable",
            })

    return _build_manifest(
        agent_name=agent_name,
        version_label=version_label,
        model=model or {"provider": "google", "model": "gemini-2.0-flash"},
        tools=tools,
        nodes=nodes,
        edges=edges,
        extra_tags=["langgraph", "auto-generated"],
    )


def _build_manifest(
    *,
    agent_name: str,
    version_label: str,
    model: dict[str, Any],
    tools: list[dict[str, Any]],
    nodes: list[str],
    edges: list[list[str]],
    extra_tags: list[str],
) -> dict[str, Any]:
    """Assemble a manifest with real surface fingerprints and computed hashes."""
    manifest = {
        "spec_version": "1.0.0",
        "kind": "agent_manifest",
        "manifest_id": mint_id("agent_manifest"),  # canonical amf_<ULID>
        "agent_name": agent_name,
        "version_label": version_label,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "description": f"Generated from LangGraph for {agent_name}",
        "tags": extra_tags,
        "identity": {"overall_hash": "", "hash_algorithm": "jcs-sha256"},
        "contract": {
            "prompt_stack": {"reasoning_policy": "hidden"},
            "model_runtime": model,
            "tool_registry": {
                "registry_version": "1",
                "registry_hash": hash_surface(tools),          # hash of the tool set
                "tools": tools,
            },
            "workflow": {
                "graph_name": f"{agent_name}-graph",
                "graph_version": "1",
                "graph_hash": hash_surface({"nodes": nodes, "edges": edges}),  # topology hash
            },
            "output_contract": {
                "version": "1",
                "schema_hash": hash_surface({"format": "text", "strict": False}),
                "format": "text",
                "strict": False,
            },
        },
        "extensions": {"langgraph": {"nodes": nodes, "edges": edges}},
    }
    compute_and_set_hashes(manifest)  # fills per-surface hashes + identity.overall_hash
    return manifest


# --- Usage with a real LangGraph agent (uncomment) ---
#
# from langgraph.graph import StateGraph
#
# builder = StateGraph(dict)
# builder.add_node("router", router_fn)
# builder.add_node("research", research_fn)
# builder.add_edge("router", "research")
# graph = builder.compile()
#
# manifest = extract_manifest_from_langgraph(graph, agent_name="research-agent", version_label="v3")
# result = validate_manifest(manifest)
# print(f"Valid: {result.valid}")
# with open("research-agent.agentversion.json", "w") as f:
#     json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    print("LangGraph integration example")
    print("=" * 40)
    print("Building a representative manifest (no LangGraph required) and validating it.\n")

    # A stand-in for what extract_manifest_from_langgraph() returns from a real graph.
    demo = _build_manifest(
        agent_name="demo-agent",
        version_label="v1",
        model={"provider": "google", "model": "gemini-2.0-flash"},
        tools=[
            {"name": "search", "version": "1",
             "hash": hash_surface({"name": "search", "args": ["query"]}), "stability": "stable"},
            {"name": "calculator", "version": "1",
             "hash": hash_surface({"name": "calculator", "args": ["expr"]}), "stability": "stable"},
        ],
        nodes=["router", "search_node", "math_node"],
        edges=[["router", "search_node"], ["router", "math_node"]],
        extra_tags=["langgraph", "demo"],
    )

    result = validate_manifest(demo)
    print(f"Valid: {result.valid}  (overall_hash {demo['identity']['overall_hash'][:23]}…)\n")
    print(json.dumps(demo, indent=2))
