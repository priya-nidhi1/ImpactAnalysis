"""Turn raw Tableau metadata into graph nodes/edges, and bridge to Databricks.

Emits:
  * datasource / field / calc-field / worksheet / dashboard nodes
  * ``maps_to``      databricks column -> tableau field   (the cross-system bridge)
  * ``computed_from`` field -> calculated field            (parsed from formulas)
  * ``used_in``      field -> worksheet -> dashboard
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ..connectors.base import RawMetadata
from ..model import (
    Edge,
    EdgeType,
    Node,
    NodeType,
    System,
    column_id_from_fqn,
    tab_calc_id,
    tab_dashboard_id,
    tab_datasource_id,
    tab_field_id,
    tab_worksheet_id,
)

_FIELD_REF = re.compile(r"\[([^\]]+)\]")


def extract_tableau(
    raw: RawMetadata,
    default_catalog: str = "insurance",
    default_schema: str = "policy",
) -> Tuple[List[Node], List[Edge]]:
    nodes: List[Node] = []
    edges: List[Edge] = []

    # (datasource, field_name_lower) -> node id, for resolving references by name
    field_index: Dict[Tuple[str, str], str] = {}
    worksheet_ids: Dict[str, str] = {}

    for ds in raw.get("datasources", []):
        ds_name = ds["name"]
        ds_id = tab_datasource_id(ds_name)
        nodes.append(
            Node(id=ds_id, type=NodeType.TABLEAU_DATASOURCE, name=ds_name,
                 system=System.TABLEAU, properties={})
        )

        for f in ds.get("fields", []):
            fid = tab_field_id(ds_name, f["name"])
            nodes.append(
                Node(id=fid, type=NodeType.TABLEAU_FIELD, name=f["name"],
                     system=System.TABLEAU, properties={"datasource": ds_name})
            )
            field_index[(ds_name, f["name"].lower())] = fid
            for up in f.get("upstreamColumns", []):
                col_id = column_id_from_fqn(
                    f"{up['table']}.{up['name']}", default_catalog, default_schema
                )
                # bridge: databricks column -> tableau field
                edges.append(Edge(src=col_id, dst=fid, type=EdgeType.MAPS_TO))

        # Register calc-field node ids first so formulas can reference each other.
        for cf in ds.get("calculatedFields", []):
            cid = tab_calc_id(ds_name, cf["name"])
            nodes.append(
                Node(id=cid, type=NodeType.TABLEAU_CALC_FIELD, name=cf["name"],
                     system=System.TABLEAU,
                     properties={"datasource": ds_name, "formula": cf.get("formula", "")})
            )
            field_index[(ds_name, cf["name"].lower())] = cid

        # Now wire formula references -> computed_from edges.
        for cf in ds.get("calculatedFields", []):
            cid = tab_calc_id(ds_name, cf["name"])
            for ref in _FIELD_REF.findall(cf.get("formula", "")):
                src = field_index.get((ds_name, ref.lower()))
                if src:
                    edges.append(Edge(src=src, dst=cid, type=EdgeType.COMPUTED_FROM))

    for wb in raw.get("workbooks", []):
        for ws in wb.get("worksheets", []):
            ws_id = tab_worksheet_id(ws["name"])
            worksheet_ids[ws["name"]] = ws_id
            nodes.append(
                Node(id=ws_id, type=NodeType.TABLEAU_WORKSHEET, name=ws["name"],
                     system=System.TABLEAU,
                     properties={"workbook": wb["name"], "datasource": ws.get("datasource")})
            )
            ds_name = ws.get("datasource")
            for fname in ws.get("fields", []):
                src = field_index.get((ds_name, fname.lower()))
                if src:
                    edges.append(Edge(src=src, dst=ws_id, type=EdgeType.USED_IN))

        for db in wb.get("dashboards", []):
            db_id = tab_dashboard_id(db["name"])
            nodes.append(
                Node(id=db_id, type=NodeType.TABLEAU_DASHBOARD, name=db["name"],
                     system=System.TABLEAU, properties={"workbook": wb["name"]})
            )
            for wsname in db.get("worksheets", []):
                ws_id = worksheet_ids.get(wsname)
                if ws_id:
                    edges.append(Edge(src=ws_id, dst=db_id, type=EdgeType.USED_IN))

    return nodes, edges
