"""Build a ``GovernanceCatalog`` from the overlay file, UC tags and lineage.

Precedence (highest first):

1. **Overlay** — ``fixtures/governance/catalog.json`` (or ``governance_overlay``
   in ``config/settings.yaml``): curated, versioned with the code.
2. **Unity Catalog tags** — carried on the raw metadata as optional ``tags``
   dicts on tables, columns and (Tableau) dashboards:

   ============== ==========================================
   ``cde``         CDE name or id the column is bound to
   ``data_tier``   ``core`` | ``derived``
   ``criticality`` ``critical`` | ``standard``
   ``data_owner``  accountable owner
   ============== ==========================================

3. **Inference** — a table with inbound column lineage and no tier is ``derived``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ..config import Settings
from ..connectors.base import RawMetadata
from ..model import Edge, EdgeType, db_column_id, db_table_id, tab_dashboard_id
from .catalog import (
    CDE,
    DEFAULT_RULES,
    INFERRED,
    OVERLAY,
    UC_TAG,
    GovernanceCatalog,
)

TAG_CDE = "cde"
TAG_TIER = "data_tier"
TAG_CRITICALITY = "criticality"
TAG_OWNER = "data_owner"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def read_overlay(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text()) or {}


def _apply_overlay(cat: GovernanceCatalog, overlay: Dict[str, Any]) -> None:
    cat.rules.update(overlay.get("rules", {}) or {})
    for c in overlay.get("cdes", []) or []:
        cde = cat.add_cde(CDE(
            id=c["id"], name=c["name"], domain=c.get("domain", ""),
            definition=c.get("definition", ""), owner=c.get("owner", ""),
            steward=c.get("steward", ""), criticality=c.get("criticality", "high"),
        ))
        for nid in c.get("assets", []) or []:
            cat.bind(cde.id, nid, OVERLAY)
    for nid, attrs in (overlay.get("assets", {}) or {}).items():
        for attr in ("tier", "criticality", "owner", "label"):
            cat.set_attr(nid, attr, attrs.get(attr), OVERLAY)


def _apply_tags(cat: GovernanceCatalog, node_id: str, tags: Dict[str, str]) -> None:
    if not tags:
        return
    tags = {k.lower(): v for k, v in tags.items()}
    cat.set_attr(node_id, "tier", tags.get(TAG_TIER), UC_TAG)
    cat.set_attr(node_id, "criticality", tags.get(TAG_CRITICALITY), UC_TAG)
    cat.set_attr(node_id, "owner", tags.get(TAG_OWNER), UC_TAG)
    if tags.get(TAG_CDE):
        key = tags[TAG_CDE]
        cde = cat.find_cde(key) or cat.add_cde(CDE(id=f"cde.{_slug(key)}", name=key))
        cat.bind(cde.id, node_id, UC_TAG)


def _apply_uc_tags(cat: GovernanceCatalog, db_raw: RawMetadata,
                   tab_raw: Optional[RawMetadata]) -> None:
    catalog, schema = db_raw.get("catalog", ""), db_raw.get("schema", "")
    for t in db_raw.get("tables", []) or []:
        _apply_tags(cat, db_table_id(catalog, schema, t["name"]), t.get("tags") or {})
        for c in t.get("columns", []) or []:
            _apply_tags(cat, db_column_id(catalog, schema, t["name"], c["name"]),
                        c.get("tags") or {})
    for wb in (tab_raw or {}).get("workbooks", []) or []:
        for d in wb.get("dashboards", []) or []:
            _apply_tags(cat, tab_dashboard_id(d["name"]), d.get("tags") or {})


def _table_of(column_id: str) -> Optional[str]:
    if not column_id.startswith("db:column:"):
        return None
    return "db:table:" + column_id[len("db:column:"):].rsplit(".", 1)[0]


def _infer_tiers(cat: GovernanceCatalog, edges: Iterable[Edge]) -> None:
    for e in edges:
        if e.type == EdgeType.DERIVES_FROM:
            tid = _table_of(e.dst)
            if tid:
                cat.set_attr(tid, "tier", "derived", INFERRED)


def build_catalog(
    overlay: Dict[str, Any],
    db_raw: RawMetadata,
    tab_raw: Optional[RawMetadata] = None,
    edges: Iterable[Edge] = (),
) -> GovernanceCatalog:
    cat = GovernanceCatalog(rules=dict(DEFAULT_RULES))
    _apply_overlay(cat, overlay)
    _apply_uc_tags(cat, db_raw, tab_raw)
    _infer_tiers(cat, edges)
    return cat


def load_governance(
    settings: Settings,
    db_raw: RawMetadata,
    tab_raw: Optional[RawMetadata] = None,
    edges: Iterable[Edge] = (),
) -> GovernanceCatalog:
    return build_catalog(read_overlay(settings.governance_overlay_path),
                         db_raw, tab_raw, edges)
