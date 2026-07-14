"""Impact summary layer.

Produces an executive, human-readable summary + remediation hints from the
*structured* impact results. Uses Mosaic AI when configured; otherwise emits a
deterministic templated summary built from the same data, so the meaning is
identical offline (the LLM only changes the phrasing, never the facts).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import List, Optional

from ..config import Settings
from ..model import ChangeRequest, ImpactResult, Severity, System
from .llm import query_llm

_SYSTEM_PROMPT = (
    "You are a deployment-impact analyst. You are given a proposed Databricks "
    "schema change and a STRUCTURED, authoritative list of impacted downstream "
    "assets. Write a concise impact assessment for engineers and BI owners. Do "
    "NOT invent any asset that is not in the provided list. Cover: blast radius "
    "summary, what breaks and why, and concrete remediation steps."
)


def _counts_block(results: List[ImpactResult]) -> str:
    by_sev = Counter(r.severity.value for r in results)
    by_sys = Counter(r.system.value for r in results)
    parts = [
        f"{by_sev.get('breaking', 0)} breaking, "
        f"{by_sev.get('warning', 0)} warning, {by_sev.get('info', 0)} info",
        f"across {by_sys.get('databricks', 0)} Databricks and "
        f"{by_sys.get('tableau', 0)} Tableau assets",
    ]
    return "; ".join(parts)


def _structured_text(change: ChangeRequest, results: List[ImpactResult]) -> str:
    lines = [
        f"Change: {change.change_type.value} on {change.target_node_id}",
        f"Details: {change.details}",
        f"Impacted assets ({len(results)}): {_counts_block(results)}",
        "",
    ]
    for r in results:
        lines.append(
            f"- [{r.severity.value.upper()}] {r.system.value}:{r.asset_type.value} "
            f"'{r.asset_name}'  via  {r.reason}"
        )
    return "\n".join(lines)


def _deterministic_summary(change: ChangeRequest, results: List[ImpactResult]) -> str:
    if not results:
        return (
            f"No downstream dependents found for a {change.change_type.value} on "
            f"`{change.target_node_id}`. Safe to deploy with respect to the "
            f"analyzed Databricks SQL/views and Tableau assets."
        )

    breaking = [r for r in results if r.severity == Severity.BREAKING]
    by_system = defaultdict(list)
    for r in results:
        by_system[r.system].append(r)

    out: List[str] = []
    out.append(f"**Impact assessment — {change.change_type.value.upper()} "
               f"`{change.target_node_id.split(':')[-1]}`**")
    out.append("")
    out.append(f"**Blast radius:** {_counts_block(results)}.")
    if breaking:
        out.append(
            f"**{len(breaking)} assets will break** and need changes before deployment."
        )
    out.append("")

    for system in (System.DATABRICKS, System.TABLEAU):
        rs = by_system.get(system)
        if not rs:
            continue
        out.append(f"**{system.value.title()}**")
        for r in rs:
            out.append(f"- `{r.severity.value.upper()}` {r.asset_type.value} "
                       f"**{r.asset_name}** — {r.reason}")
        out.append("")

    out.append("**Recommended remediation:**")
    if change.change_type.value == "rename":
        out.append("- Update referencing views/queries to the new column name, then "
                   "re-point or refresh affected Tableau data sources and calculated fields.")
        out.append("- Coordinate the rename with BI owners of the breaking dashboards above.")
    elif change.change_type.value == "drop":
        out.append("- Confirm no consumer above still needs the column; provide a "
                   "replacement or deprecation window before dropping.")
    elif change.change_type.value == "retype":
        out.append("- Validate casts/aggregations in the listed views and Tableau "
                   "calculated fields against the new datatype.")
    else:
        out.append("- Review the listed consumers and validate behavior in a staging run.")
    return "\n".join(out)


def summarize_impact(
    change: ChangeRequest,
    results: List[ImpactResult],
    settings: Optional[Settings] = None,
) -> str:
    """Return an executive impact summary (Mosaic AI when available)."""
    if settings is not None:
        prompt = (
            "Proposed change and authoritative impacted-asset list follow.\n\n"
            + _structured_text(change, results)
            + "\n\nWrite the impact assessment now."
        )
        llm = query_llm(prompt, settings, system=_SYSTEM_PROMPT)
        if llm:
            return llm.strip()
    return _deterministic_summary(change, results)
