"""End-to-end impact engine tests against the sample fixtures.

Verifies exact impacted-asset sets (precision/recall = 1.0 on the labeled
fixtures), severity classification, the NL->ChangeRequest path, and the summary.
"""

import json
import pathlib

import pytest

from impact.ai.nl_change import parse_nl_change
from impact.ai.summarize import summarize_impact
from impact.config import load_settings
from impact.graph import analyze_change
from impact.model import ChangeRequest, ChangeType, Severity
from impact.pipeline import build_graph_in_memory

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def graph():
    return build_graph_in_memory(load_settings())


@pytest.fixture(scope="module")
def expected():
    return json.loads((ROOT / "fixtures" / "expected_impact.json").read_text())


def test_rename_policy_status_exact_match(graph, expected):
    exp = expected["rename_policy_status"]
    cr = ChangeRequest(exp["change"]["target"], ChangeType.RENAME)
    results = analyze_change(graph, cr)
    got = {r.asset_id for r in results}
    assert got == set(exp["expected_assets"])
    assert all(r.severity == Severity.BREAKING for r in results)
    # cross-system: both Databricks and Tableau assets impacted
    systems = {r.system.value for r in results}
    assert systems == {"databricks", "tableau"}


def test_retype_premium_amount_warning(graph, expected):
    exp = expected["retype_premium_amount"]
    cr = ChangeRequest(exp["change"]["target"], ChangeType.RETYPE)
    results = analyze_change(graph, cr)
    got = {r.asset_id for r in results}
    assert got == set(exp["expected_assets"])
    assert all(r.severity == Severity.WARNING for r in results)


def test_unreferenced_column_has_no_impact(graph):
    # customer_id is not consumed by any view/query/Tableau asset.
    cr = ChangeRequest(
        "db:column:insurance.policy.policies.customer_id", ChangeType.RENAME
    )
    assert analyze_change(graph, cr) == []


def test_nl_question_routes_to_engine(graph):
    cr = parse_nl_change("What will be impacted if I rename policy_status?", graph)
    assert cr is not None
    assert cr.change_type == ChangeType.RENAME
    assert cr.target_node_id == "db:column:insurance.policy.policies.policy_status"


def test_summary_mentions_impacted_assets(graph, expected):
    exp = expected["rename_policy_status"]
    cr = ChangeRequest(exp["change"]["target"], ChangeType.RENAME)
    results = analyze_change(graph, cr)
    summary = summarize_impact(cr, results)  # no settings -> deterministic fallback
    assert "Executive Policy Dashboard" in summary
    assert "vw_active_policies" in summary
    assert "breaking" in summary.lower()
