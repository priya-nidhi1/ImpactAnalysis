"""Build the unified dependency graph (networkx DiGraph) from nodes + edges.

The Databricks and Tableau subgraphs are joined automatically at ``maps_to``
edges, whose endpoints are canonical ids shared across systems (a Databricks
column id appears both as a column node and as the source of a ``maps_to`` edge).
"""

from __future__ import annotations

from typing import Iterable, List, Optional

import networkx as nx

from ..model import Edge, Node, NodeType


def build_graph(nodes: Iterable[Node], edges: Iterable[Edge]) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n.id, node=n)
    for e in edges:
        # Only keep edges whose endpoints both resolved to real nodes; this
        # safely drops references to objects outside the analyzed scope.
        if e.src in g.nodes and e.dst in g.nodes:
            g.add_edge(e.src, e.dst, etype=e.type.value, edge=e)
    return g


def find_nodes(
    g: nx.DiGraph,
    *,
    name: Optional[str] = None,
    type: Optional[NodeType] = None,
) -> List[Node]:
    """Lookup helper for the UI / NL layer (case-insensitive name contains)."""
    out: List[Node] = []
    needle = name.lower() if name else None
    for _, data in g.nodes(data=True):
        node: Node = data["node"]
        if type is not None and node.type != type:
            continue
        if needle is not None and needle not in node.name.lower() and needle not in node.id.lower():
            continue
        out.append(node)
    return out
