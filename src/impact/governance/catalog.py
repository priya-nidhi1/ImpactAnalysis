"""Governance catalog: critical data elements, table tiers, report criticality.

A ``GovernanceCatalog`` answers three questions about any graph node id:

* which critical data elements (CDEs) is it bound to?  (a CDE is a business
  concept, e.g. "Policy status", that may span many physical assets)
* is it a *core* or *derived* data product?            (tables)
* is it a *critical* business report?                  (dashboards)

Every attribute remembers where it came from (``overlay`` | ``uc_tag`` |
``inferred``) so reviewers can see how much of an assessment is curated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import networkx as nx

OVERLAY = "overlay"
UC_TAG = "uc_tag"
INFERRED = "inferred"

DEFAULT_RULES: Dict[str, Any] = {
    "high_min_dimensions": 2,              # breaking + >= N flagged dimensions
    "high_on_breaking_critical_report": True,
    "high_on_all_dimensions": True,        # all three flagged, even non-breaking
    "medium_min_dimensions": 1,
}


@dataclass
class CDE:
    id: str
    name: str
    domain: str = ""
    definition: str = ""
    owner: str = ""
    steward: str = ""
    criticality: str = "high"
    assets: List[str] = field(default_factory=list)
    asset_sources: Dict[str, str] = field(default_factory=dict)

    def ref(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "domain": self.domain,
                "owner": self.owner, "steward": self.steward,
                "criticality": self.criticality}


@dataclass
class AssetGovernance:
    tier: Optional[str] = None          # "core" | "derived"
    criticality: Optional[str] = None   # "critical" | "standard"
    owner: Optional[str] = None
    label: Optional[str] = None         # business-friendly name
    sources: Dict[str, str] = field(default_factory=dict)  # attr -> provenance


@dataclass
class GovernanceCatalog:
    cdes: Dict[str, CDE] = field(default_factory=dict)
    assets: Dict[str, AssetGovernance] = field(default_factory=dict)
    rules: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_RULES))

    # ---- mutation (used by the loader) ------------------------------------ #
    def add_cde(self, cde: CDE) -> CDE:
        return self.cdes.setdefault(cde.id, cde)

    def find_cde(self, key: str) -> Optional[CDE]:
        """Resolve a CDE by id or (case-insensitive) name, e.g. from a UC tag."""
        k = key.strip().lower()
        for c in self.cdes.values():
            if c.id.lower() == k or c.name.lower() == k:
                return c
        return None

    def bind(self, cde_id: str, node_id: str, source: str) -> None:
        cde = self.cdes[cde_id]
        if node_id not in cde.assets:
            cde.assets.append(node_id)
            cde.asset_sources[node_id] = source

    def set_attr(self, node_id: str, attr: str, value: Any, source: str) -> None:
        """Set ``attr`` unless a higher-precedence source already did."""
        if value in (None, ""):
            return
        a = self.assets.setdefault(node_id, AssetGovernance())
        if getattr(a, attr) is None:
            setattr(a, attr, value)
            a.sources[attr] = source

    # ---- lookups ---------------------------------------------------------- #
    def cdes_for(self, node_id: str) -> List[CDE]:
        return [c for c in self.cdes.values() if node_id in c.assets]

    def asset(self, node_id: str) -> AssetGovernance:
        return self.assets.get(node_id) or AssetGovernance()

    def tier(self, node_id: str) -> Optional[str]:
        return self.asset(node_id).tier

    def is_critical(self, node_id: str) -> bool:
        return self.asset(node_id).criticality == "critical"

    # ---- reconstruction from an enriched graph ---------------------------- #
    @classmethod
    def from_graph(cls, g: nx.DiGraph) -> "GovernanceCatalog":
        """Rebuild a catalog from node properties stamped by ``apply_governance``.

        Lets a graph loaded from the store be assessed without re-reading the
        overlay or Unity Catalog tags.
        """
        cat = cls(rules=dict(g.graph.get("governance_rules") or DEFAULT_RULES))
        for nid, data in g.nodes(data=True):
            props = data["node"].properties
            src = props.get("governance_sources", {}) or {}
            for ref in props.get("cdes", []) or []:
                cat.add_cde(CDE(**{k: ref.get(k, "") for k in
                                   ("id", "name", "domain", "owner", "steward",
                                    "criticality")}))
                cat.bind(ref["id"], nid, src.get("cde:" + ref["id"], OVERLAY))
            for attr in ("tier", "criticality", "owner", "label"):
                cat.set_attr(nid, attr, props.get(attr), src.get(attr, OVERLAY))
        return cat
