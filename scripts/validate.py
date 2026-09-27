"""Precision/recall of the impact engine vs the hand-labeled fixtures.

Run:  python scripts/validate.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from impact.config import Settings, load_settings  # noqa: E402
from impact.governance import assess_impact  # noqa: E402
from impact.graph import analyze_change  # noqa: E402
from impact.model import ChangeRequest, ChangeType  # noqa: E402
from impact.pipeline import build_graph_in_memory  # noqa: E402


def precision_recall(settings: Settings | None = None) -> List[str]:
    settings = settings or load_settings()
    g = build_graph_in_memory(settings)
    labels = json.loads((ROOT / "fixtures" / "expected_impact.json").read_text())

    lines: List[str] = []
    tp_all = fp_all = fn_all = gov_fail = 0
    for name, spec in labels.items():
        cr = ChangeRequest(
            spec["change"]["target"], ChangeType(spec["change"]["change_type"])
        )
        results = analyze_change(g, cr)
        predicted = {r.asset_id for r in results}
        expected = set(spec["expected_assets"])
        tp = len(predicted & expected)
        fp = len(predicted - expected)
        fn = len(expected - predicted)
        tp_all, fp_all, fn_all = tp_all + tp, fp_all + fp, fn_all + fn
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 1.0
        lines.append(f"{name:28s} precision={prec:.2f} recall={rec:.2f} "
                     f"(tp={tp} fp={fp} fn={fn})")
        gov_exp = spec.get("expected_governance")
        if gov_exp:
            mismatches = governance_mismatches(assess_impact(g, cr, results), gov_exp)
            gov_fail += bool(mismatches)
            lines.append(f"{'':28s} governance "
                         + ("ok" if not mismatches else "MISMATCH " + "; ".join(mismatches)))

    prec = tp_all / (tp_all + fp_all) if (tp_all + fp_all) else 1.0
    rec = tp_all / (tp_all + fn_all) if (tp_all + fn_all) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    lines.append("-" * 60)
    lines.append(f"OVERALL  precision={prec:.2f}  recall={rec:.2f}  f1={f1:.2f}  "
                 f"governance_mismatches={gov_fail}")
    return lines


def governance_mismatches(a, exp) -> List[str]:
    """Compare an ImpactAssessment against an ``expected_governance`` label."""
    got = {
        "rating": a.rating.value,
        "cdes": sorted(c["name"] for c in a.cdes),
        "downstream_tables": a.kpis["downstream_tables"],
        "core_tables": a.kpis["core_tables"],
        "critical_reports": sorted(r["name"] for r in a.critical_reports),
    }
    want = {k: sorted(v) if isinstance(v, list) else v for k, v in exp.items()}
    return [f"{k}: expected {want[k]!r}, got {got[k]!r}" for k in want if got.get(k) != want[k]]


if __name__ == "__main__":
    out = precision_recall()
    for line in out:
        print(line)
    if not out[-1].endswith("governance_mismatches=0"):
        sys.exit(1)
