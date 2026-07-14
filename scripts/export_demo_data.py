"""Precompute the static-site demo data from the real impact engine.

Runs the deterministic engine over the sample fixtures and exports every
``column x change-type`` scenario (impact results + offline summary) to
``docs/demo/data.json``, which the static demo page renders. Also copies the
prototype plan into ``docs/`` so the docs site has a single source of truth.

Run:  python scripts/export_demo_data.py
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["IMPACT_MODE"] = "sample"  # the site is always fixture-backed

from impact.ai.summarize import summarize_impact  # noqa: E402
from impact.config import load_settings  # noqa: E402
from impact.graph import analyze_change  # noqa: E402
from impact.model import ChangeRequest, ChangeType, NodeType  # noqa: E402
from impact.pipeline import build_graph_in_memory  # noqa: E402

OUT = ROOT / "docs" / "demo-app" / "data.json"
PLAN_SRC = ROOT / "ImpactAnalysisPrototypePlan.md"
PLAN_DST = ROOT / "docs" / "prototype-plan.md"

CHANGE_LABELS = {
    ChangeType.ADD: "Add column",
    ChangeType.DROP: "Drop column",
    ChangeType.RENAME: "Rename column",
    ChangeType.RETYPE: "Change datatype",
    ChangeType.LOGIC: "Change logic",
}


def _validation_lines(settings) -> list:
    """Load scripts/validate.py as a module and reuse its harness."""
    spec = importlib.util.spec_from_file_location(
        "validate", ROOT / "scripts" / "validate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.precision_recall(settings)


def main() -> None:
    settings = load_settings()
    graph = build_graph_in_memory(settings)

    columns = sorted(
        (d["node"].name, nid)
        for nid, d in graph.nodes(data=True)
        if d["node"].type == NodeType.COLUMN
    )

    scenarios = {}
    for _, col_id in columns:
        for ctype in ChangeType:
            change = ChangeRequest(col_id, ctype)
            results = analyze_change(graph, change)
            scenarios[f"{col_id}|{ctype.value}"] = {
                # settings=None -> always the deterministic offline summary
                "summary": summarize_impact(change, results, None),
                "results": [
                    {
                        "severity": r.severity.value,
                        "system": r.system.value,
                        "type": r.asset_type.value,
                        "asset": r.asset_name,
                        "reason": r.reason,
                        "path": r.path,
                    }
                    for r in results
                ],
            }

    default_col = next(
        (nid for name, nid in columns if name == "policies.policy_status"),
        columns[0][1] if columns else None,
    )

    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "mode": settings.mode,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "columns": [{"id": nid, "label": name} for name, nid in columns],
        "change_types": [
            {"value": c.value, "label": CHANGE_LABELS[c]} for c in ChangeType
        ],
        "default_column": default_col,
        "default_change": ChangeType.RENAME.value,
        "validation": _validation_lines(settings),
        "scenarios": scenarios,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1))
    shutil.copyfile(PLAN_SRC, PLAN_DST)

    print(f"wrote {OUT.relative_to(ROOT)}  "
          f"({len(columns)} columns x {len(ChangeType)} change types = "
          f"{len(scenarios)} scenarios, {OUT.stat().st_size // 1024} KB)")
    print(f"copied {PLAN_SRC.name} -> {PLAN_DST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
