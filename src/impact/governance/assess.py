"""Governance impact assessment.

Rolls a change's downstream reach up into the view a change advisory board
needs: which critical data elements are touched, how many downstream tables
(and how many *core* tables) depend on the field, which critical business
reports are exposed, an overall High / Medium / Low rating with its rationale,
and a review focus.

Deterministic like the impact engine: it reuses the same downstream walk, so
the assessment always agrees with the per-asset ``ImpactResult`` list.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

import networkx as nx

from ..evidence import table_logic
from ..graph.impact import downstream_reach
from ..model import (
    ChangeRequest,
    ImpactAssessment,
    ImpactRating,
    ImpactResult,
    Node,
    NodeType,
    Severity,
    db_table_id,
)
from .catalog import INFERRED, GovernanceCatalog

_SEMANTIC_TYPES = {NodeType.VIEW, NodeType.QUERY, NodeType.TABLEAU_FIELD,
                   NodeType.TABLEAU_DATASOURCE}

_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight",
          "nine", "ten", "eleven", "twelve"]


def _num(n: int, capital: bool = False) -> str:
    w = _WORDS[n] if n < len(_WORDS) else str(n)
    return w.capitalize() if capital else w


def _plural(n: int, word: str, plural: Optional[str] = None) -> str:
    return word if n == 1 else (plural or word + "s")


def _join(items: List[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _table_id_of(node: Node) -> Optional[str]:
    p = node.properties
    if node.type == NodeType.COLUMN and p.get("table"):
        return db_table_id(p["catalog"], p["schema"], p["table"])
    if node.type == NodeType.TABLE:
        return node.id
    return None


def _pretty_table(name: str) -> str:
    return name.split(".")[-1].replace("_", " ").capitalize()


def resolve_catalog(g: nx.DiGraph,
                    catalog: Optional[GovernanceCatalog] = None) -> GovernanceCatalog:
    if catalog is not None:
        return catalog
    return g.graph.get("governance") or GovernanceCatalog.from_graph(g)


def assess_impact(
    g: nx.DiGraph,
    change: ChangeRequest,
    results: List[ImpactResult],
    catalog: Optional[GovernanceCatalog] = None,
) -> ImpactAssessment:
    catalog = resolve_catalog(g, catalog)
    start = change.target_node_id
    in_graph = start in g.nodes
    source: Optional[Node] = g.nodes[start]["node"] if in_graph else None
    source_name = source.name if source else start.split(":")[-1]
    order = downstream_reach(g, start)[1] if in_graph else []
    reached = ([start] if in_graph else []) + order
    severity_by_id = {r.asset_id: r.severity for r in results}
    provenance: Counter = Counter()

    # -- critical data elements -------------------------------------------- #
    cde_hits: Dict[str, Dict[str, Any]] = {}
    for nid in reached:
        for cde in catalog.cdes_for(nid):
            hit = cde_hits.setdefault(cde.id, {**cde.ref(), "assets": []})
            hit["assets"].append(g.nodes[nid]["node"].name)
            provenance[cde.asset_sources.get(nid) or INFERRED] += 1
    source_cdes = [c.ref() for c in catalog.cdes_for(start)]

    # -- downstream data products (tables) ----------------------------------- #
    source_table = _table_id_of(source) if source else None
    reached_columns = [n for n in reached if n.startswith("db:column:")]
    tables: Dict[str, Dict[str, Any]] = {}
    for nid in order:
        tid = _table_id_of(g.nodes[nid]["node"])
        if not tid or tid == source_table or tid in tables or tid not in g.nodes:
            continue
        gov = catalog.asset(tid)
        tier = gov.tier or "derived"      # reached via lineage => derived
        provenance[gov.sources.get("tier", INFERRED)] += 1
        tname = g.nodes[tid]["node"].name
        tables[tid] = {"id": tid, "name": tname,
                       "label": gov.label or _pretty_table(tname),
                       "tier": tier, "owner": gov.owner or "",
                       "source": gov.sources.get("tier", INFERRED),
                       "logic": table_logic(g, tid, reached_columns)}
    downstream_tables = list(tables.values())

    # -- reporting components and business reports -------------------------- #
    semantic, calcs, worksheets, reports = [], [], [], []
    for nid in order:
        node: Node = g.nodes[nid]["node"]
        sev = severity_by_id.get(nid)
        item = {"id": nid, "name": node.name, "type": node.type.value,
                "severity": sev.value if sev else None,
                "cdes": [c.name for c in catalog.cdes_for(nid)]}
        if node.type in _SEMANTIC_TYPES:
            semantic.append(item)
        elif node.type == NodeType.TABLEAU_CALC_FIELD:
            calcs.append(item)
        elif node.type == NodeType.TABLEAU_WORKSHEET:
            worksheets.append(item)
        elif node.type == NodeType.TABLEAU_DASHBOARD:
            gov = catalog.asset(nid)
            if gov.criticality:
                provenance[gov.sources.get("criticality", INFERRED)] += 1
            reports.append({**item, "criticality": gov.criticality or "standard",
                            "owner": gov.owner or ""})
    critical_reports = [{"id": r["id"], "name": r["name"], "owner": r["owner"]}
                        for r in reports if r["criticality"] == "critical"]

    core = [t for t in downstream_tables if t["tier"] == "core"]
    cdes = list(cde_hits.values())

    # -- rationale dimensions ------------------------------------------------ #
    if cdes:
        cde_detail = (f"The change touches governed "
                      f"{_join([c['name'].lower() for c in cdes])} "
                      f"{_plural(len(cdes), 'definition')}.")
    else:
        cde_detail = "No critical data elements are bound to the field or its consumers."

    n_tab = len(downstream_tables)
    if core:
        core_detail = (f"{_num(n_tab, True)} {_plural(n_tab, 'table')} "
                       f"{_plural(n_tab, 'depends', 'depend')} on the field, including "
                       f"{_num(len(core))} core {_plural(len(core), 'table')}.")
    elif n_tab:
        core_detail = (f"{_num(n_tab, True)} derived {_plural(n_tab, 'table')} "
                       f"{_plural(n_tab, 'depends', 'depend')} on the field; "
                       f"no core tables.")
    else:
        core_detail = "No downstream tables depend on the field."

    if critical_reports:
        n = len(critical_reports)
        rep_detail = (f"{'A critical dashboard depends' if n == 1 else _num(n, True) + ' critical dashboards depend'}"
                      f" on the affected reporting logic.")
    elif reports:
        rep_detail = (f"{_num(len(reports), True)} {_plural(len(reports), 'dashboard')} "
                      f"affected; none classified critical.")
    else:
        rep_detail = "No dashboards are affected."

    dimensions = [
        {"name": "CDE Criticality", "flagged": bool(cdes), "detail": cde_detail},
        {"name": "Core Data Dependency", "flagged": bool(core), "detail": core_detail},
        {"name": "Critical Reporting", "flagged": bool(critical_reports),
         "detail": rep_detail},
    ]

    # -- overall rating ------------------------------------------------------ #
    rules = catalog.rules
    flagged = sum(d["flagged"] for d in dimensions)
    breaking = any(r.severity == Severity.BREAKING for r in results)
    # A non-breaking change can still be High: a logic change to a CDE that
    # feeds core tables and a critical report silently shifts governed numbers.
    if (breaking and (
        flagged >= rules.get("high_min_dimensions", 2)
        or (critical_reports and rules.get("high_on_breaking_critical_report", True))
    )) or (flagged == len(dimensions) and rules.get("high_on_all_dimensions", True)):
        rating = ImpactRating.HIGH
    elif breaking or flagged >= rules.get("medium_min_dimensions", 1):
        rating = ImpactRating.MEDIUM
    else:
        rating = ImpactRating.LOW

    # -- review focus -------------------------------------------------------- #
    actions = []
    if cdes:
        actions.append("confirm CDE mappings and ownership")
    if downstream_tables or semantic:
        actions.append("validate the dependency paths")
    if calcs or worksheets or reports:
        actions.append("test the affected reporting logic")
    if actions:
        review_focus = _join(actions)
        review_focus = review_focus[0].upper() + review_focus[1:] + "."
    else:
        review_focus = "No downstream dependencies found; standard change review applies."

    owners: List[str] = []
    for c in cdes:
        for who, role in ((c.get("owner"), "owner"), (c.get("steward"), "steward")):
            if who:
                owners.append(f"{who} ({c['name']} {role})")
    for t in core:
        if t["owner"]:
            owners.append(f"{t['owner']} ({t['label']} owner)")
    for r in critical_reports:
        if r["owner"]:
            owners.append(f"{r['owner']} ({r['name']} owner)")
    owners = list(dict.fromkeys(owners))

    layers = {
        "source": {"id": start, "name": source_name, "cdes": [c["name"] for c in source_cdes],
                   "type": source.type.value if source else None},
        "data_products": {"core": core,
                          "derived": [t for t in downstream_tables if t["tier"] != "core"]},
        "reporting_components": {"semantic": semantic, "calculations": calcs,
                                 "worksheets": worksheets},
        "business_reports": reports,
    }

    return ImpactAssessment(
        change=change,
        source_name=source_name,
        source_cdes=source_cdes,
        rating=rating,
        cdes=cdes,
        downstream_tables=downstream_tables,
        critical_reports=critical_reports,
        layers=layers,
        dimensions=dimensions,
        review_focus=review_focus,
        owners=owners,
        provenance=dict(provenance),
    )
