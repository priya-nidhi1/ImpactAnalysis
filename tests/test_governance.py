"""Governance layer tests: CDE identification, core/derived tiers, critical
reports, overall impact rating and overlay-vs-UC-tag precedence."""

import pytest

from impact.config import load_settings
from impact.governance import GovernanceCatalog, assess_impact, build_catalog
from impact.governance.catalog import INFERRED, OVERLAY, UC_TAG
from impact.graph import analyze_change
from impact.model import ChangeRequest, ChangeType, Edge, EdgeType, ImpactRating
from impact.pipeline import analyze_with_governance, build_graph_in_memory

POLICY_STATUS = "db:column:insurance.policy.policies.policy_status"


@pytest.fixture(scope="module")
def graph():
    return build_graph_in_memory(load_settings())


def _assess(graph, target, change_type):
    cr = ChangeRequest(target, change_type)
    return assess_impact(graph, cr, analyze_change(graph, cr))


def test_rename_policy_status_matches_governance_scenario(graph):
    a = _assess(graph, POLICY_STATUS, ChangeType.RENAME)
    assert a.rating == ImpactRating.HIGH
    assert a.kpis == {"cdes": 2, "downstream_tables": 8, "core_tables": 2,
                      "critical_reports": 1}
    assert {c["name"] for c in a.cdes} == {"Policy status", "Renewal eligibility"}
    assert {t["label"] for t in a.core_tables} == {"Policy master", "Policy term"}
    assert len(a.derived_tables) == 6
    assert [r["name"] for r in a.critical_reports] == ["Executive Policy Dashboard"]
    assert all(d["flagged"] for d in a.dimensions)
    assert [c["name"] for c in a.source_cdes] == ["Policy status"]
    focus = a.review_focus.lower()
    assert "cde mappings" in focus and "dependency paths" in focus \
        and "reporting logic" in focus


def test_cde_calculation_is_flagged_in_reporting_layer(graph):
    a = _assess(graph, POLICY_STATUS, ChangeType.RENAME)
    calcs = {c["name"]: c for c in a.layers["reporting_components"]["calculations"]}
    assert calcs["Renewal Eligible Flag"]["cdes"] == ["Renewal eligibility"]
    assert calcs["Active Flag"]["cdes"] == []


def test_unreferenced_column_is_low(graph):
    a = _assess(graph, "db:column:insurance.policy.policies.customer_id",
                ChangeType.RENAME)
    assert a.rating == ImpactRating.LOW
    assert a.kpis == {"cdes": 0, "downstream_tables": 0, "core_tables": 0,
                      "critical_reports": 0}
    assert not any(d["flagged"] for d in a.dimensions)


def test_non_breaking_change_to_critical_report_is_medium(graph):
    a = _assess(graph, "db:column:insurance.policy.policies.premium_amount",
                ChangeType.RETYPE)
    assert a.rating == ImpactRating.MEDIUM
    assert a.kpis["critical_reports"] == 1
    assert [c["name"] for c in a.cdes] == ["Premium amount"]


def test_logic_change_on_all_dimensions_is_high(graph):
    a = _assess(graph, POLICY_STATUS, ChangeType.LOGIC)
    assert a.rating == ImpactRating.HIGH


def test_new_column_has_no_assessment_impact(graph):
    a = _assess(graph, "db:column:insurance.policy.policies.risk_score", ChangeType.ADD)
    assert a.rating == ImpactRating.LOW
    assert a.downstream_tables == []


def test_nodes_are_enriched_with_governance(graph):
    col = graph.nodes[POLICY_STATUS]["node"].properties
    assert [c["name"] for c in col["cdes"]] == ["Policy status"]
    term = graph.nodes["db:column:insurance.policy.policy_term.term_status"]["node"]
    assert term.properties["table_tier"] == "core"
    dash = graph.nodes["tab:dashboard:Executive Policy Dashboard"]["node"]
    assert dash.properties["criticality"] == "critical"


def test_overlay_beats_uc_tag_and_tag_only_values_are_used(graph):
    cat: GovernanceCatalog = graph.graph["governance"]
    master = cat.asset("db:table:insurance.policy.policy_master")
    assert master.owner == "Policy Data Office"          # overlay over data_owner tag
    assert master.sources["owner"] == OVERLAY
    term = cat.asset("db:table:insurance.policy.policy_term")
    assert term.tier == "core" and term.sources["tier"] == UC_TAG
    status = cat.find_cde("Policy status")
    term_col = "db:column:insurance.policy.policy_term.term_status"
    assert status.asset_sources[term_col] == UC_TAG      # bound only via column tag


def test_tier_inferred_from_lineage_and_unknown_tag_creates_cde():
    raw = {
        "catalog": "c", "schema": "s",
        "tables": [
            {"name": "a", "columns": [{"name": "x", "tags": {"cde": "Brand New CDE"}}]},
            {"name": "b", "columns": [{"name": "y"}]},
        ],
    }
    edges = [Edge("db:column:c.s.a.x", "db:column:c.s.b.y", EdgeType.DERIVES_FROM)]
    cat = build_catalog({}, raw, None, edges)
    assert cat.tier("db:table:c.s.b") == "derived"
    assert cat.asset("db:table:c.s.b").sources["tier"] == INFERRED
    assert cat.tier("db:table:c.s.a") is None
    cde = cat.find_cde("brand new cde")
    assert cde is not None and cde.assets == ["db:column:c.s.a.x"]


def test_analyze_with_governance_round_trip(graph):
    cr = ChangeRequest(POLICY_STATUS, ChangeType.RENAME)
    results, a = analyze_with_governance(cr, graph=graph)
    assert results and a.rating == ImpactRating.HIGH
    d = a.to_dict()
    assert d["rating"] == "high" and d["kpis"]["core_tables"] == 2


def test_catalog_rebuilds_from_persisted_node_properties(graph):
    rebuilt = GovernanceCatalog.from_graph(graph)
    a = assess_impact(graph, ChangeRequest(POLICY_STATUS, ChangeType.RENAME),
                      analyze_change(graph, ChangeRequest(POLICY_STATUS,
                                                          ChangeType.RENAME)),
                      catalog=rebuilt)
    assert a.kpis == {"cdes": 2, "downstream_tables": 8, "core_tables": 2,
                      "critical_reports": 1}
