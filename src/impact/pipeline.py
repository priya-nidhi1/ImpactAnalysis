"""End-to-end orchestration: connector -> extract -> store -> graph -> impact.

Used by the notebooks, the Streamlit app and the tests so they all share one
code path.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import networkx as nx

from .config import Settings, load_settings
from .connectors import get_connector
from .extract import (
    extract_databricks,
    extract_sql,
    extract_tableau,
    schema_map_from_raw,
)
from .graph import analyze_change, build_graph
from .model import ChangeRequest, Edge, ImpactResult, Node
from .store import MetadataStore, get_store


def extract_all(settings: Settings) -> Tuple[List[Node], List[Edge]]:
    """Pull metadata from the active connector and normalize to nodes/edges."""
    connector = get_connector(settings)
    db_raw = connector.get_databricks_metadata()
    tab_raw = connector.get_tableau_metadata()

    nodes: List[Node] = []
    edges: List[Edge] = []

    n1, e1 = extract_databricks(db_raw)
    nodes += n1
    edges += e1

    n2, e2 = extract_sql(
        db_raw, dialect=settings.sql_dialect, schema_map=schema_map_from_raw(db_raw)
    )
    nodes += n2
    edges += e2

    n3, e3 = extract_tableau(
        tab_raw,
        default_catalog=settings.default_catalog,
        default_schema=settings.default_schema,
    )
    nodes += n3
    edges += e3

    return _dedupe_nodes(nodes), edges


def _dedupe_nodes(nodes: List[Node]) -> List[Node]:
    seen = {}
    for n in nodes:
        seen.setdefault(n.id, n)
    return list(seen.values())


def merge_into_store(
    store: MetadataStore, nodes: List[Node], edges: List[Edge]
) -> None:
    """Union new nodes/edges into whatever the store already holds.

    Lets the staged notebooks (10 Databricks, then 20 Tableau) each persist
    their slice without clobbering the other.
    """
    by_id = {n.id: n for n in store.read_nodes()}
    for n in nodes:
        by_id[n.id] = n

    seen = set()
    merged_edges: List[Edge] = []
    for e in list(store.read_edges()) + list(edges):
        key = (e.src, e.dst, e.type.value)
        if key in seen:
            continue
        seen.add(key)
        merged_edges.append(e)

    store.write_nodes(list(by_id.values()))
    store.write_edges(merged_edges)


def build_repository(
    settings: Optional[Settings] = None, store: Optional[MetadataStore] = None
) -> Tuple[List[Node], List[Edge]]:
    """Extract and persist the dependency repository, returning nodes/edges."""
    settings = settings or load_settings()
    store = store or get_store(settings)
    nodes, edges = extract_all(settings)
    store.write_repository(nodes, edges)
    return nodes, edges


def load_graph(
    settings: Optional[Settings] = None, store: Optional[MetadataStore] = None
) -> nx.DiGraph:
    """Load persisted nodes/edges into a graph."""
    settings = settings or load_settings()
    store = store or get_store(settings)
    return build_graph(store.read_nodes(), store.read_edges())


def build_graph_in_memory(settings: Optional[Settings] = None) -> nx.DiGraph:
    """Extract and build a graph without touching storage (app/tests)."""
    settings = settings or load_settings()
    nodes, edges = extract_all(settings)
    return build_graph(nodes, edges)


def analyze(
    change: ChangeRequest,
    settings: Optional[Settings] = None,
    graph: Optional[nx.DiGraph] = None,
    store: Optional[MetadataStore] = None,
    persist: bool = False,
) -> List[ImpactResult]:
    settings = settings or load_settings()
    graph = graph if graph is not None else build_graph_in_memory(settings)
    results = analyze_change(graph, change)
    if persist:
        store = store or get_store(settings)
        store.write_records("change_requests", [change.to_dict()])
        store.write_records("impact_results", [r.to_dict() for r in results])
    return results
