"""Code-level evidence: *where* and *how* each hop of an impact path happens.

For every hop on an impact path this returns the underlying logic and the
exact line numbers that consume the upstream object:

* ``references``    column -> view/query       view / query SQL
* ``derives_from``  column -> derived column   the target table's definition SQL
* ``computed_from`` field  -> calculated field Tableau formula
* ``maps_to``       column -> Tableau field    the field-to-column mapping
* ``used_in``       field  -> worksheet -> dashboard (placement, no code)

SQL line numbers come from sqlglot's token positions, resolved through table
aliases, so ``c.policy_id`` is not mistaken for ``p.policy_id``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

import networkx as nx
import sqlglot
from sqlglot import exp

from .model import EdgeType, Node, NodeType, db_table_id

_KIND_LABEL = {
    NodeType.VIEW: "view",
    NodeType.QUERY: "query",
    NodeType.TABLE: "table",
    NodeType.TABLEAU_FIELD: "Tableau field",
    NodeType.TABLEAU_CALC_FIELD: "calculated field",
    NodeType.TABLEAU_WORKSHEET: "worksheet",
    NodeType.TABLEAU_DASHBOARD: "dashboard",
}


def _column_fq(node_id: str) -> Optional[str]:
    return node_id[len("db:column:"):] if node_id.startswith("db:column:") else None


def _word_lines(text: str, word: str) -> List[int]:
    pat = re.compile(rf"(?<![\w.]){re.escape(word)}(?!\w)|\.{re.escape(word)}(?!\w)",
                     re.IGNORECASE)
    return [i for i, line in enumerate(text.splitlines(), 1) if pat.search(line)]


def sql_reference_lines(sql: str, column_fqs: Iterable[str],
                        dialect: str = "databricks") -> List[int]:
    """1-based line numbers in ``sql`` that reference any of ``column_fqs``.

    ``column_fqs`` are ``catalog.schema.table.column`` strings.
    """
    targets = {}
    for fq in column_fqs:
        cat, sch, tbl, col = fq.lower().split(".")
        targets.setdefault(col, set()).add(f"{cat}.{sch}.{tbl}")
    if not sql or not targets:
        return []
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception:
        tree = None
    if tree is None:
        return sorted({n for col in targets for n in _word_lines(sql, col)})

    alias_to_fq: Dict[str, str] = {}
    for tbl in tree.find_all(exp.Table):
        name = tbl.name.lower()
        # Unqualified names resolve to whatever the column's table lives in.
        fq = ".".join(p.lower() for p in (tbl.catalog, tbl.db) if p)
        fq = f"{fq}.{name}" if fq else name
        alias_to_fq[(tbl.alias_or_name or name).lower()] = fq
        alias_to_fq[name] = fq
    tables_in_scope = set(alias_to_fq.values())

    def _matches(fq_or_name: str, wanted: set) -> bool:
        return any(w == fq_or_name or w.endswith("." + fq_or_name) for w in wanted)

    lines = set()
    for col in tree.find_all(exp.Column):
        wanted = targets.get(col.name.lower())
        if not wanted:
            continue
        qual = (col.table or "").lower()
        if qual:
            hit = qual in alias_to_fq and _matches(alias_to_fq[qual], wanted)
        else:
            hit = any(_matches(t, wanted) for t in tables_in_scope)
        line = col.this.meta.get("line") if isinstance(col.this, exp.Expression) else None
        if hit and line:
            lines.add(line)
    if not lines and any(isinstance(s, exp.Star) for s in tree.find_all(exp.Star)):
        # SELECT * : the dependency is the star itself.
        lines.update(i for i, l in enumerate(sql.splitlines(), 1) if "*" in l)
    return sorted(lines)


def formula_reference_lines(formula: str, field_name: str) -> List[int]:
    needle = f"[{field_name.lower()}]"
    return [i for i, line in enumerate((formula or "").splitlines(), 1)
            if needle in line.lower()]


def _snippet(obj: str, kind: str, language: str, code: str, lines: List[int],
             **extra: Any) -> Dict[str, Any]:
    return {"object": obj, "kind": kind, "language": language, "code": code,
            "lines": lines, **extra}


def hop_evidence(g: nx.DiGraph, src_id: str, dst_id: str,
                 changed_columns: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """Evidence for one producer -> consumer edge, or None for structural hops.

    ``changed_columns`` widens the highlighted SQL lines to every changed
    column when a whole table is changed (not just the first one reached).
    """
    changed = [c for c in changed_columns if c != src_id]
    etype = g.edges[src_id, dst_id]["etype"]
    src: Node = g.nodes[src_id]["node"]
    dst: Node = g.nodes[dst_id]["node"]
    base = {"from": src.name, "to": dst.name, "relation": etype}

    if etype == EdgeType.REFERENCES.value:
        sql = dst.properties.get("sql", "")
        fqs = [f for f in map(_column_fq, [src_id, *changed]) if f]
        lines = sql_reference_lines(sql, fqs)
        return {**base, **_snippet(dst.name, "sql", "sql", sql, lines,
                                   title=f"{_KIND_LABEL.get(dst.type, 'asset')} "
                                         f"{dst.name} reads {src.name}")}

    if etype == EdgeType.DERIVES_FROM.value:
        p = dst.properties
        tid = db_table_id(p.get("catalog", ""), p.get("schema", ""), p.get("table", ""))
        table = g.nodes[tid]["node"] if tid in g.nodes else None
        sql = table.properties.get("sql", "") if table else ""
        title = f"{p.get('table', dst.name)}.{p.get('column', '')} derives from {src.name}"
        if not sql:
            return {**base, **_snippet(dst.name, "lineage", "text",
                                       f"{_column_fq(src_id)}  →  {_column_fq(dst_id)}",
                                       [], title=title,
                                       note="Column lineage only; no table definition "
                                            "is available for this table.")}
        fqs = [f for f in map(_column_fq, [src_id, *changed]) if f]
        return {**base, **_snippet(table.name, "sql", "sql", sql,
                                   sql_reference_lines(sql, fqs), title=title)}

    if etype == EdgeType.COMPUTED_FROM.value:
        formula = dst.properties.get("formula", "")
        return {**base, **_snippet(dst.name, "formula", "tableau", formula,
                                   formula_reference_lines(formula, src.name),
                                   title=f"calculated field {dst.name} computes from "
                                         f"[{src.name}]")}

    if etype == EdgeType.MAPS_TO.value:
        ds = dst.properties.get("datasource", "")
        return {**base, **_snippet(dst.name, "mapping", "text",
                                   f"[{ds}].[{dst.name}]  ⇐  {_column_fq(src_id)}", [],
                                   title=f"Tableau field {dst.name} maps to {src.name}")}

    if etype == EdgeType.USED_IN.value:
        return {**base, **_snippet(dst.name, "usage", "text", "", [],
                                   title=f"{src.name} is used in "
                                         f"{_KIND_LABEL.get(dst.type, 'asset')} {dst.name}")}
    return None  # contains: table -> column, purely structural


def trace_evidence(g: nx.DiGraph, preds: Dict[str, Optional[str]],
                   target: str) -> List[Dict[str, Any]]:
    """Hop-by-hop evidence from the changed node to ``target``."""
    chain: List[str] = []
    cur: Optional[str] = target
    while cur is not None:
        chain.append(cur)
        cur = preds.get(cur)
    chain.reverse()
    root: Node = g.nodes[chain[0]]["node"]
    changed = ([c for c in g.successors(root.id) if c.startswith("db:column:")]
               if root.type == NodeType.TABLE else [])
    out = []
    for a, b in zip(chain, chain[1:]):
        # Widen only the first data hop out of a changed table.
        ev = hop_evidence(g, a, b, changed if a in changed else ())
        if ev:
            out.append(ev)
    return out


def table_logic(g: nx.DiGraph, table_id: str,
                upstream_columns: Iterable[str]) -> Optional[Dict[str, Any]]:
    """A table's definition with the lines that read any of ``upstream_columns``."""
    if table_id not in g.nodes:
        return None
    table: Node = g.nodes[table_id]["node"]
    sql = table.properties.get("sql", "")
    if not sql:
        return None
    fqs = [f for f in (_column_fq(c) for c in upstream_columns) if f]
    return _snippet(table.name, "sql", "sql", sql, sql_reference_lines(sql, fqs),
                    title=f"{table.name} definition")


def numbered(code: str, lines: Iterable[int]) -> List[Dict[str, Any]]:
    """``[{"n", "text", "hit"}]`` for rendering code with highlighted lines."""
    hits = set(lines)
    return [{"n": i, "text": t, "hit": i in hits}
            for i, t in enumerate(code.splitlines() or [code], 1)]
