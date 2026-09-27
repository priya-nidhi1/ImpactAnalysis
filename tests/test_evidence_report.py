"""Code evidence (line numbers + calculation logic) and downloadable reports."""

import csv
import io

import pytest

from impact.config import load_settings
from impact.evidence import formula_reference_lines, sql_reference_lines
from impact.governance import assess_impact
from impact.graph import analyze_change
from impact.model import ChangeRequest, ChangeType
from impact.pipeline import analyze_with_governance, build_graph_in_memory
from impact.report import line_refs, report_html, results_csv
from impact.store.delta import LocalJsonStore

POLICY_STATUS = "db:column:insurance.policy.policies.policy_status"


@pytest.fixture(scope="module")
def graph():
    return build_graph_in_memory(load_settings())


@pytest.fixture(scope="module")
def rename(graph):
    cr = ChangeRequest(POLICY_STATUS, ChangeType.RENAME)
    results = analyze_change(graph, cr)
    return cr, results, assess_impact(graph, cr, results)


def _by_name(results):
    return {r.asset_name: r for r in results}


def test_sql_lines_resolve_aliases():
    sql = ("SELECT\n  p.policy_id,\n  c.claim_id\nFROM insurance.policy.policies AS p\n"
           "JOIN insurance.policy.claims AS c\n  ON p.policy_id = c.policy_id")
    # c.policy_id (line 6) matches claims, p.policy_id (lines 2 and 6) does not.
    assert sql_reference_lines(sql, ["insurance.policy.claims.policy_id"]) == [6]
    assert sql_reference_lines(sql, ["insurance.policy.policies.policy_id"]) == [2, 6]
    assert sql_reference_lines(sql, ["insurance.policy.policies.claim_id"]) == []


def test_formula_lines():
    assert formula_reference_lines('IF [Policy Status] = "A"\nTHEN 1 END',
                                   "policy status") == [1]


def test_view_evidence_points_at_referencing_lines(rename):
    _, results, _ = rename
    ev = _by_name(results)["policy.vw_policy_summary"].evidence
    assert len(ev) == 1 and ev[0]["kind"] == "sql"
    code = ev[0]["code"].splitlines()
    assert ev[0]["lines"] == [3, 10]
    assert all("p.policy_status" in code[n - 1] for n in ev[0]["lines"])


def test_calc_evidence_traces_through_derived_tables(rename):
    _, results, _ = rename
    ev = _by_name(results)["Renewal Eligible Flag"].evidence
    assert [e["kind"] for e in ev] == ["sql", "sql", "mapping", "formula"]
    assert ev[0]["object"] == "policy.policy_master"
    assert ev[1]["object"] == "policy.renewal_eligibility"
    assert "m.policy_status" in ev[1]["code"].splitlines()[ev[1]["lines"][0] - 1]
    assert ev[-1]["code"] == "IF [Renewal Eligibility] THEN 1 ELSE 0 END"
    assert ev[-1]["lines"] == [1]


def test_table_level_change_highlights_every_changed_column(graph):
    cr = ChangeRequest("db:table:insurance.policy.claims", ChangeType.DROP)
    ev = _by_name(analyze_change(graph, cr))["policy.vw_policy_summary"].evidence
    code = ev[0]["code"].splitlines()
    assert ev[0]["lines"] == [4, 7]          # c.claim_id and the c.policy_id join key
    assert all("c." in code[n - 1] for n in ev[0]["lines"])


def test_downstream_tables_carry_definition_logic(rename):
    _, _, a = rename
    logic = {t["label"]: t["logic"] for t in a.downstream_tables}
    assert logic["Renewal eligibility"]["lines"] == [4, 5, 10]
    assert logic["Policy master"]["lines"] == [3]


def test_line_refs_compacts_ranges():
    assert line_refs([9, 3, 4, 5]) == "L3–L5, L9"
    assert line_refs([]) == ""


def test_html_report_contents(rename):
    cr, results, a = rename
    doc = report_html(cr, results, a)
    assert doc.startswith("<!doctype html>")
    for text in ("Change Impact Report", "high impact", "Executive Policy Dashboard",
                 "Renewal eligibility", "Data product logic", "Review focus",
                 'class="hit"', "IF [Renewal Eligibility] THEN 1 ELSE 0 END"):
        assert text in doc, text
    assert "<script" not in doc


def test_csv_report(rename):
    cr, results, a = rename
    rows = list(csv.DictReader(io.StringIO(results_csv(results, a))))
    assert len(rows) == len(results)
    by = {r["asset_name"]: r for r in rows}
    assert by["policy.vw_active_policies"]["logic_locations"] == \
        "policy.vw_active_policies L3, L7"
    assert by["Executive Policy Dashboard"]["critical_report"] == "yes"
    assert by["Renewal Eligible Flag"]["cdes"] == "Renewal eligibility"


def test_persisting_assessment(graph, tmp_path):
    store = LocalJsonStore(tmp_path)
    cr = ChangeRequest(POLICY_STATUS, ChangeType.RENAME)
    analyze_with_governance(cr, graph=graph, store=store, persist=True)
    saved = store.read_records("impact_assessments")
    assert saved[0]["kpis"]["downstream_tables"] == 8
    assert store.read_records("impact_results")[0]["evidence"]


@pytest.mark.parametrize("engine", ["weasyprint", "xhtml2pdf"])
def test_pdf_report(rename, engine):
    pytest.importorskip(engine)
    pypdf = pytest.importorskip("pypdf")
    from impact.report_pdf import pdf_engine, report_pdf

    if engine == "weasyprint" and pdf_engine() != "weasyprint":
        pytest.skip("WeasyPrint's Pango system library is not installed")
    cr, results, a = rename
    data = report_pdf(cr, results, a, engine=engine)
    assert data.startswith(b"%PDF")
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(data)).pages)
    text = " ".join(text.split())
    for needle in ("Change Impact Report", "HIGH IMPACT", "Executive Policy Dashboard",
                   "DATA PRODUCT LOGIC", "Review focus", "Renewal Eligible Flag",
                   "IF [Renewal Eligibility] THEN 1 ELSE 0 END"):
        assert needle.lower() in text.lower(), needle


def test_pdf_report_without_impact(graph):
    pytest.importorskip("xhtml2pdf")
    from impact.report_pdf import report_pdf

    cr = ChangeRequest("db:column:insurance.policy.policies.customer_id", ChangeType.RENAME)
    results = analyze_change(graph, cr)
    pdf = report_pdf(cr, results, assess_impact(graph, cr, results), engine="xhtml2pdf")
    assert pdf.startswith(b"%PDF")


def test_forced_engine_is_validated(monkeypatch):
    from impact.report_pdf import pdf_engine

    pdf_engine.cache_clear()
    monkeypatch.setenv("IMPACT_PDF_ENGINE", "xhtml2pdf")
    assert pdf_engine() == "xhtml2pdf"
    pdf_engine.cache_clear()
    monkeypatch.setenv("IMPACT_PDF_ENGINE", "nope")
    with pytest.raises(ValueError):
        pdf_engine()
    pdf_engine.cache_clear()
