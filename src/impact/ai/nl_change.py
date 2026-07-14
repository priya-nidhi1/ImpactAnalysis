"""Natural-language -> ChangeRequest.

Turns a question like *"What breaks if I rename policy_status?"* into a
structured ``ChangeRequest`` that feeds the deterministic engine. When a Mosaic
AI endpoint is configured it is used to extract intent as JSON; the extracted
target is then **validated against the real graph** so the LLM can never invent
an object. A keyword-based resolver is the always-available fallback.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import networkx as nx

from ..config import Settings
from ..model import ChangeRequest, ChangeType, NodeType
from .llm import query_llm

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_CHANGE_KEYWORDS = [
    (ChangeType.RENAME, ("rename", "renaming", "rename to")),
    (ChangeType.DROP, ("drop", "remove", "delete")),
    (ChangeType.RETYPE, ("datatype", "data type", "retype", "change the type",
                         "change type", "cast")),
    (ChangeType.ADD, ("add ", "new column", "introduce")),
    (ChangeType.LOGIC, ("logic", "definition", "recalculate", "transformation")),
]


def _detect_change_type(text: str) -> ChangeType:
    t = text.lower()
    for ctype, kws in _CHANGE_KEYWORDS:
        if any(kw in t for kw in kws):
            return ctype
    return ChangeType.RENAME  # safe default for "what breaks if I change X"


def _detect_target(text: str, graph: nx.DiGraph) -> Optional[str]:
    tokens = {w.lower() for w in _WORD.findall(text)}
    best = None  # (score, length, node_id)
    for _, data in graph.nodes(data=True):
        node = data["node"]
        if node.type == NodeType.COLUMN:
            col = (node.properties.get("column") or "").lower()
            tbl = (node.properties.get("table") or "").lower()
            if col and col in tokens:
                score = (2 if tbl in tokens else 1, len(col))
                if best is None or score > best[0]:
                    best = (score, node.id)
    if best:
        return best[1]
    # Fall back to table-level match.
    for _, data in graph.nodes(data=True):
        node = data["node"]
        if node.type == NodeType.TABLE:
            tbl = (node.properties.get("table") or "").lower()
            if tbl and tbl in tokens:
                return node.id
    return None


def _try_llm(text: str, graph: nx.DiGraph, settings: Settings) -> Optional[ChangeRequest]:
    prompt = (
        "Extract the intended schema change from this question as strict JSON "
        'with keys "object" (the column or table name), "change_type" '
        '(one of add/drop/rename/retype/logic) and optional "new_name". '
        f"Question: {text!r}. Return only JSON."
    )
    raw = query_llm(prompt, settings, max_tokens=120)
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(0) if m else raw)
        ctype = ChangeType(data["change_type"].lower())
    except Exception:
        return None
    # Validate the object against the graph (no hallucinated targets).
    obj = str(data.get("object", ""))
    target = _detect_target(obj, graph) or _detect_target(text, graph)
    if not target:
        return None
    details = {"new_name": data["new_name"]} if data.get("new_name") else {}
    return ChangeRequest(target_node_id=target, change_type=ctype, details=details)


def parse_nl_change(
    text: str, graph: nx.DiGraph, settings: Optional[Settings] = None
) -> Optional[ChangeRequest]:
    if settings is not None and settings.model_endpoint:
        cr = _try_llm(text, graph, settings)
        if cr:
            return cr

    target = _detect_target(text, graph)
    if not target:
        return None
    ctype = _detect_change_type(text)
    details = {}
    if ctype == ChangeType.RENAME:
        m = re.search(r"\bto\s+([A-Za-z_][A-Za-z0-9_]*)", text)
        if m:
            details["new_name"] = m.group(1)
    return ChangeRequest(target_node_id=target, change_type=ctype, details=details)
