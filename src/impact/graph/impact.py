"""Deterministic impact engine.

Given a ``ChangeRequest`` targeting a column or table node, walk the graph
downstream (producer -> consumer) to collect every dependent asset, classify a
severity, and record the path that explains *why* it is impacted.

This module is the source of truth: the LLM layer only phrases these results.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional

import networkx as nx

from ..model import (
    ChangeRequest,
    ChangeType,
    EdgeType,
    ImpactResult,
    Node,
    NodeType,
    REPORTABLE_TYPES,
    Severity,
)

# Base severity by change type for any reachable consumer.
_BASE_SEVERITY = {
    ChangeType.DROP: Severity.BREAKING,
    ChangeType.RENAME: Severity.BREAKING,
    ChangeType.RETYPE: Severity.WARNING,
    ChangeType.LOGIC: Severity.WARNING,
    ChangeType.ADD: Severity.INFO,
}

# Human labels for edge relationships in the explanation path.
_REL_LABEL = {
    EdgeType.CONTAINS.value: "contains",
    EdgeType.DERIVES_FROM.value: "derives",
    EdgeType.REFERENCES.value: "referenced by",
    EdgeType.MAPS_TO.value: "feeds",
    EdgeType.COMPUTED_FROM.value: "computes",
    EdgeType.USED_IN.value: "used in",
}


def _severity_for(node: Node, change_type: ChangeType) -> Severity:
    sev = _BASE_SEVERITY[change_type]
    # A datatype change that reaches a calculated field or dashboard is more
    # likely to actually break rendering/aggregation -> escalate to BREAKING.
    if change_type == ChangeType.RETYPE and node.type in (
        NodeType.TABLEAU_CALC_FIELD,
    ):
        return Severity.BREAKING
    return sev


def _build_path(
    g: nx.DiGraph, preds: Dict[str, Optional[str]], start: str, target: str
) -> List[str]:
    chain: List[str] = []
    cur: Optional[str] = target
    while cur is not None:
        chain.append(cur)
        cur = preds.get(cur)
    chain.reverse()  # start ... target

    parts: List[str] = [g.nodes[chain[0]]["node"].name]
    for a, b in zip(chain, chain[1:]):
        rel = _REL_LABEL.get(g.edges[a, b]["etype"], "->")
        parts.append(f"--{rel}-->")
        parts.append(g.nodes[b]["node"].name)
    return parts


def analyze_change(g: nx.DiGraph, change: ChangeRequest) -> List[ImpactResult]:
    start = change.target_node_id
    if start not in g.nodes:
        # ADD of a brand-new column legitimately has no existing dependents.
        return []

    # BFS over directed edges, tracking predecessors for path reconstruction.
    preds: Dict[str, Optional[str]] = {start: None}
    order: List[str] = []
    q = deque([start])
    while q:
        cur = q.popleft()
        for succ in g.successors(cur):
            if succ not in preds:
                preds[succ] = cur
                order.append(succ)
                q.append(succ)

    results: List[ImpactResult] = []
    for nid in order:
        node: Node = g.nodes[nid]["node"]
        if node.type not in REPORTABLE_TYPES:
            continue  # hide structural intermediates (raw columns, etc.)
        severity = _severity_for(node, change.change_type)
        path = _build_path(g, preds, start, nid)
        results.append(
            ImpactResult(
                asset_id=nid,
                asset_name=node.name,
                asset_type=node.type,
                system=node.system,
                severity=severity,
                reason=" ".join(path),
                path=path,
            )
        )

    # Most severe first, then by system for stable grouping.
    results.sort(key=lambda r: (-r.severity.rank, r.system.value, r.asset_name))
    return results
