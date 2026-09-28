"""Stamp governance attributes onto graph nodes.

After enrichment every node carries, in ``Node.properties``:

* ``cdes``        list of CDE refs bound to the node (``[]`` when none)
* ``tier`` / ``criticality`` / ``owner`` / ``label`` when governed
* ``table_tier``  for columns: the tier of their parent table
* ``governance_sources`` attr -> provenance (overlay | uc_tag | inferred)

Storing these on the node means the persisted repository, the graph and the
UI all see the same governance view without any schema change.
"""

from __future__ import annotations

from typing import List

from ..model import Node, NodeType, db_table_id
from .catalog import GovernanceCatalog


def apply_governance(nodes: List[Node], catalog: GovernanceCatalog) -> List[Node]:
    for n in nodes:
        props = n.properties
        sources = {}
        cdes = catalog.cdes_for(n.id)
        props["cdes"] = [c.ref() for c in cdes]
        for c in cdes:
            sources["cde:" + c.id] = c.asset_sources.get(n.id, "")
        a = catalog.assets.get(n.id)
        if a:
            for attr in ("tier", "criticality", "owner", "label"):
                val = getattr(a, attr)
                if val is not None:
                    props[attr] = val
                    sources[attr] = a.sources.get(attr, "")
        if n.type == NodeType.COLUMN and props.get("table"):
            tier = catalog.tier(db_table_id(props["catalog"], props["schema"],
                                            props["table"]))
            if tier:
                props["table_tier"] = tier
        if sources:
            props["governance_sources"] = sources
    return nodes
