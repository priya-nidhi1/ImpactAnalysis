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
from impact.graph import analyze_change  # noqa: E402
from impact.model import ChangeRequest, ChangeType  # noqa: E402
from impact.pipeline import build_graph_in_memory  # noqa: E402


def precision_recall(settings: Settings | None = None) -> List[str]:
    settings = settings or load_settings()
    g = build_graph_in_memory(settings)
    labels = json.loads((ROOT / "fixtures" / "expected_impact.json").read_text())

    lines: List[str] = []
    tp_all = fp_all = fn_all = 0
    for name, spec in labels.items():
        cr = ChangeRequest(
            spec["change"]["target"], ChangeType(spec["change"]["change_type"])
        )
        predicted = {r.asset_id for r in analyze_change(g, cr)}
        expected = set(spec["expected_assets"])
        tp = len(predicted & expected)
        fp = len(predicted - expected)
        fn = len(expected - predicted)
        tp_all, fp_all, fn_all = tp_all + tp, fp_all + fp, fn_all + fn
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 1.0
        lines.append(f"{name:28s} precision={prec:.2f} recall={rec:.2f} "
                     f"(tp={tp} fp={fp} fn={fn})")

    prec = tp_all / (tp_all + fp_all) if (tp_all + fp_all) else 1.0
    rec = tp_all / (tp_all + fn_all) if (tp_all + fn_all) else 1.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    lines.append("-" * 60)
    lines.append(f"OVERALL  precision={prec:.2f}  recall={rec:.2f}  f1={f1:.2f}")
    return lines


if __name__ == "__main__":
    for line in precision_recall():
        print(line)
