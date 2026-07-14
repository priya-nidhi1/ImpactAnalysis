"""Unified graph data model — the "dependency repository".

Everything (Databricks tables/columns/views/queries and Tableau
datasources/fields/worksheets/dashboards) is normalized into ``Node`` and
``Edge`` records so a single graph traversal can answer cross-system impact.

Edge direction convention (important): edges always point from
**producer -> consumer**, i.e. ``A -> B`` means "if A changes, B is impacted".
This lets impact analysis be a plain reachability walk from the changed node.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class System(str, enum.Enum):
    DATABRICKS = "databricks"
    TABLEAU = "tableau"


class NodeType(str, enum.Enum):
    CATALOG = "catalog"
    SCHEMA = "schema"
    TABLE = "table"
    VIEW = "view"
    COLUMN = "column"
    QUERY = "query"
    TABLEAU_DATASOURCE = "tableau_datasource"
    TABLEAU_FIELD = "tableau_field"
    TABLEAU_CALC_FIELD = "tableau_calc_field"
    TABLEAU_WORKSHEET = "tableau_worksheet"
    TABLEAU_DASHBOARD = "tableau_dashboard"


class EdgeType(str, enum.Enum):
    CONTAINS = "contains"            # table -> column
    DERIVES_FROM = "derives_from"    # upstream column -> downstream column
    REFERENCES = "references"        # column -> view/query that reads it
    MAPS_TO = "maps_to"              # databricks column -> tableau field (bridge)
    COMPUTED_FROM = "computed_from"  # field -> calculated field
    USED_IN = "used_in"             # field -> worksheet -> dashboard


class ChangeType(str, enum.Enum):
    ADD = "add"
    DROP = "drop"
    RENAME = "rename"
    RETYPE = "retype"      # datatype change
    LOGIC = "logic"        # logic / transformation change


class Severity(str, enum.Enum):
    BREAKING = "breaking"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"breaking": 3, "warning": 2, "info": 1}[self.value]


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    id: str
    type: NodeType
    name: str                 # human-friendly display name
    system: System
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        d["system"] = self.system.value
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Node":
        return Node(
            id=d["id"],
            type=NodeType(d["type"]),
            name=d["name"],
            system=System(d["system"]),
            properties=d.get("properties", {}) or {},
        )


@dataclass
class Edge:
    src: str
    dst: str
    type: EdgeType
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Edge":
        return Edge(
            src=d["src"],
            dst=d["dst"],
            type=EdgeType(d["type"]),
            properties=d.get("properties", {}) or {},
        )


@dataclass
class ChangeRequest:
    """A proposed schema change to evaluate."""

    target_node_id: str
    change_type: ChangeType
    details: Dict[str, Any] = field(default_factory=dict)  # e.g. {"new_name": ...}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["change_type"] = self.change_type.value
        return d


@dataclass
class ImpactResult:
    asset_id: str
    asset_name: str
    asset_type: NodeType
    system: System
    severity: Severity
    reason: str
    path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["asset_type"] = self.asset_type.value
        d["system"] = self.system.value
        d["severity"] = self.severity.value
        return d


# --------------------------------------------------------------------------- #
# Canonical node-id helpers
# --------------------------------------------------------------------------- #
# Databricks identifiers are case-insensitive and stored lowercase, so we
# normalize them. Tableau names are case-sensitive and kept as-is.
def _norm(s: str) -> str:
    return s.strip().lower()


def db_table_id(catalog: str, schema: str, table: str) -> str:
    return f"db:table:{_norm(catalog)}.{_norm(schema)}.{_norm(table)}"


def db_view_id(catalog: str, schema: str, view: str) -> str:
    return f"db:view:{_norm(catalog)}.{_norm(schema)}.{_norm(view)}"


def db_column_id(catalog: str, schema: str, table: str, column: str) -> str:
    return f"db:column:{_norm(catalog)}.{_norm(schema)}.{_norm(table)}.{_norm(column)}"


def db_query_id(query_id: str) -> str:
    return f"db:query:{query_id}"


def column_id_from_fqn(fqn: str, default_catalog: str, default_schema: str) -> str:
    """Build a column node id from a (possibly partial) ``a.b.c.d`` reference.

    Accepts ``table.column``, ``schema.table.column`` or
    ``catalog.schema.table.column`` and fills in defaults.
    """
    parts = [p for p in fqn.replace("`", "").split(".") if p]
    if len(parts) == 4:
        cat, sch, tbl, col = parts
    elif len(parts) == 3:
        cat, sch, tbl, col = default_catalog, parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        cat, sch, tbl, col = default_catalog, default_schema, parts[0], parts[1]
    else:
        raise ValueError(f"Cannot resolve column reference: {fqn!r}")
    return db_column_id(cat, sch, tbl, col)


def tab_datasource_id(name: str) -> str:
    return f"tab:datasource:{name}"


def tab_field_id(datasource: str, field_name: str) -> str:
    return f"tab:field:{datasource}.{field_name}"


def tab_calc_id(datasource: str, field_name: str) -> str:
    return f"tab:calc:{datasource}.{field_name}"


def tab_worksheet_id(name: str) -> str:
    return f"tab:worksheet:{name}"


def tab_dashboard_id(name: str) -> str:
    return f"tab:dashboard:{name}"


# Node types that count as "downstream consumers" worth reporting in an
# impact assessment (we hide pure structural nodes like raw columns/tables
# unless they are the changed object itself).
REPORTABLE_TYPES = {
    NodeType.VIEW,
    NodeType.QUERY,
    NodeType.TABLEAU_DATASOURCE,
    NodeType.TABLEAU_FIELD,
    NodeType.TABLEAU_CALC_FIELD,
    NodeType.TABLEAU_WORKSHEET,
    NodeType.TABLEAU_DASHBOARD,
}
