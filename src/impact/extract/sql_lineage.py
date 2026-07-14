"""Column-level SQL lineage via sqlglot.

``referenced_columns`` parses a SQL statement, qualifies every column against
the known table schema (resolving aliases and expanding ``*``), and returns the
set of fully-qualified ``catalog.schema.table.column`` references. This is what
makes Databricks SQL/view impact *real* rather than only query-history-derived.

``extract_sql`` uses it to emit ``references`` edges (column -> view/query).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

from ..connectors.base import RawMetadata
from ..model import (
    Edge,
    EdgeType,
    Node,
    NodeType,
    System,
    db_query_id,
    db_view_id,
)
from .databricks_meta import schema_map_from_raw


def _nested_schema(schema_map: Dict[str, List[str]]) -> dict:
    """Convert flat ``{cat.sch.tbl: [cols]}`` to sqlglot's nested schema."""
    nested: dict = {}
    for fq, cols in schema_map.items():
        cat, sch, tbl = fq.split(".")
        nested.setdefault(cat, {}).setdefault(sch, {}).setdefault(tbl, {})
        for c in cols:
            nested[cat][sch][tbl][c.lower()] = "UNKNOWN"
    return nested


def referenced_columns(
    sql: str,
    dialect: str,
    default_catalog: str,
    default_schema: str,
    schema_map: Dict[str, List[str]],
) -> Set[str]:
    if not sql or not sql.strip():
        return set()
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        return set()
    if tree is None:
        return set()

    nested = _nested_schema(schema_map)
    try:
        tree = qualify(
            tree,
            schema=nested,
            dialect=dialect,
            catalog=default_catalog,
            db=default_schema,
            qualify_columns=True,
            validate_qualify_columns=False,
            expand_stars=True,
        )
    except Exception:
        pass  # fall back to the un-qualified tree

    # Map every table alias / name in scope to its fully-qualified table.
    alias_to_fq: Dict[str, str] = {}
    for tbl in tree.find_all(exp.Table):
        cat = (tbl.catalog or default_catalog).lower()
        db = (tbl.db or default_schema).lower()
        name = tbl.name.lower()
        fq = f"{cat}.{db}.{name}"
        alias_to_fq[(tbl.alias_or_name or tbl.name).lower()] = fq
        alias_to_fq[name] = fq

    distinct_tables = set(alias_to_fq.values())
    cols: Set[str] = set()
    for col in tree.find_all(exp.Column):
        col_name = col.name
        if not col_name:
            continue
        qualifier = (col.table or "").lower()
        if qualifier and qualifier in alias_to_fq:
            cols.add(f"{alias_to_fq[qualifier]}.{col_name.lower()}")
        elif len(distinct_tables) == 1:
            # Unqualified column in a single-table query.
            cols.add(f"{next(iter(distinct_tables))}.{col_name.lower()}")
    return cols


def extract_sql(
    raw: RawMetadata,
    dialect: Optional[str] = None,
    schema_map: Optional[Dict[str, List[str]]] = None,
) -> Tuple[List[Node], List[Edge]]:
    catalog = raw["catalog"]
    schema = raw["schema"]
    dialect = dialect or "databricks"
    schema_map = schema_map if schema_map is not None else schema_map_from_raw(raw)

    nodes: List[Node] = []
    edges: List[Edge] = []

    def add_refs(target_id: str, sql: str) -> None:
        for fq in referenced_columns(sql, dialect, catalog, schema, schema_map):
            edges.append(
                Edge(src=f"db:column:{fq}", dst=target_id, type=EdgeType.REFERENCES)
            )

    for v in raw.get("views", []):
        add_refs(db_view_id(catalog, schema, v["name"]), v.get("sql", ""))

    for q in raw.get("queries", []):
        qid = db_query_id(q["id"])
        nodes.append(
            Node(
                id=qid,
                type=NodeType.QUERY,
                name=q["id"],
                system=System.DATABRICKS,
                properties={"sql": q.get("sql", ""), "source": q.get("source", "")},
            )
        )
        add_refs(qid, q.get("sql", ""))

    # Optional raw column lineage (system.access.column_lineage) -> derives_from
    for lin in raw.get("column_lineage", []) or []:
        src = f"db:column:{lin['source'].lower()}"
        dst = f"db:column:{lin['target'].lower()}"
        edges.append(Edge(src=src, dst=dst, type=EdgeType.DERIVES_FROM))

    return nodes, edges
