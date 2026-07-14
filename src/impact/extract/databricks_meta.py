"""Turn raw Databricks metadata into graph nodes/edges.

Produces table, view and column nodes plus ``contains`` (table -> column) edges.
View ``references`` edges are added by :mod:`impact.extract.sql_lineage`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..connectors.base import RawMetadata
from ..model import (
    Edge,
    EdgeType,
    Node,
    NodeType,
    System,
    db_column_id,
    db_table_id,
    db_view_id,
)


def schema_map_from_raw(raw: RawMetadata) -> Dict[str, List[str]]:
    """Build ``{"catalog.schema.table": [col, ...]}`` for SQL qualification."""
    catalog = raw["catalog"]
    schema = raw["schema"]
    out: Dict[str, List[str]] = {}
    for t in raw.get("tables", []):
        key = f"{catalog}.{schema}.{t['name']}".lower()
        out[key] = [c["name"] for c in t.get("columns", [])]
    return out


def extract_databricks(raw: RawMetadata) -> Tuple[List[Node], List[Edge]]:
    catalog = raw["catalog"]
    schema = raw["schema"]
    nodes: List[Node] = []
    edges: List[Edge] = []

    for t in raw.get("tables", []):
        tname = t["name"]
        tid = db_table_id(catalog, schema, tname)
        nodes.append(
            Node(
                id=tid,
                type=NodeType.TABLE,
                name=f"{schema}.{tname}",
                system=System.DATABRICKS,
                properties={"catalog": catalog, "schema": schema,
                            "table_type": t.get("type", "TABLE")},
            )
        )
        for c in t.get("columns", []):
            cid = db_column_id(catalog, schema, tname, c["name"])
            nodes.append(
                Node(
                    id=cid,
                    type=NodeType.COLUMN,
                    name=f"{tname}.{c['name']}",
                    system=System.DATABRICKS,
                    properties={"catalog": catalog, "schema": schema,
                                "table": tname, "column": c["name"],
                                "data_type": c.get("type", "")},
                )
            )
            edges.append(Edge(src=tid, dst=cid, type=EdgeType.CONTAINS))

    for v in raw.get("views", []):
        vid = db_view_id(catalog, schema, v["name"])
        nodes.append(
            Node(
                id=vid,
                type=NodeType.VIEW,
                name=f"{schema}.{v['name']}",
                system=System.DATABRICKS,
                properties={"catalog": catalog, "schema": schema,
                            "sql": v.get("sql", "")},
            )
        )

    return nodes, edges
