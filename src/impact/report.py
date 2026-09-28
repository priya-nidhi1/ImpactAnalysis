"""Downloadable impact reports: an HTML template (rendered to PDF) and CSV.

``report_html`` builds a single self-contained HTML document: the governance
roll-up, the layered downstream flow, data-product logic, and every impacted
asset with its path and line-numbered SQL / formula logic, with the lines that
reference the changed field highlighted. :mod:`impact.report_pdf` turns it
into the PDF download.

The template is deliberately "print-safe" so every PDF engine renders it the
same: layout uses tables (no grid / flex), colours are literal values (no CSS
variables), and code indentation uses non-breaking spaces (no ``pre-wrap``).
It also reads fine opened directly in a browser.
"""

from __future__ import annotations

import csv
import html
import io
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .evidence import numbered
from .model import ChangeRequest, ImpactAssessment, ImpactResult

_e = html.escape

PROVENANCE_LABEL = {"overlay": "from the governance overlay",
                    "uc_tag": "from Unity Catalog tags",
                    "inferred": "inferred from lineage"}


def report_basename(change: ChangeRequest, when: Optional[datetime] = None) -> str:
    when = when or datetime.now(timezone.utc)
    obj = change.target_node_id.split(":")[-1].split(".")[-1]
    return f"impact_{change.change_type.value}_{obj}_{when:%Y%m%d_%H%M}"


def line_refs(lines: Iterable[int]) -> str:
    """``[3, 4, 5, 9]`` -> ``"L3–L5, L9"``."""
    out, run = [], []
    for n in sorted(set(lines)):
        if run and n == run[-1] + 1:
            run.append(n)
            continue
        if run:
            out.append(f"L{run[0]}" if len(run) == 1 else f"L{run[0]}–L{run[-1]}")
        run = [n]
    if run:
        out.append(f"L{run[0]}" if len(run) == 1 else f"L{run[0]}–L{run[-1]}")
    return ", ".join(out)


def evidence_locations(result: ImpactResult) -> str:
    """``"policy.vw_active_policies L3, L7; Active Flag L1"`` for tables/CSV."""
    return "; ".join(f"{e['object']} {line_refs(e['lines'])}"
                     for e in result.evidence if e.get("lines"))


def _code_text(text: str) -> str:
    # Leading spaces become &nbsp; so indentation survives without pre-wrap.
    stripped = text.lstrip(" ")
    return "&nbsp;" * (len(text) - len(stripped)) + _e(stripped) if text else "&nbsp;"


def code_block_html(code: str, lines: Iterable[int], cls: str = "code") -> str:
    """Line-numbered code with the referencing lines highlighted."""
    rows = "".join(
        f'<tr class="{"hit" if r["hit"] else ""}"><td class="ln">{r["n"]}</td>'
        f'<td class="src">{_code_text(r["text"])}</td></tr>'
        for r in numbered(code, lines)
    )
    return f'<table class="{cls}">{rows}</table>'


def evidence_html(evidence: List[Dict[str, Any]], cls: str = "code") -> str:
    parts = []
    for i, ev in enumerate(evidence, 1):
        refs = line_refs(ev.get("lines", []))
        head = (f'<div class="hop"><span class="hop-n">{i}</span> '
                f'<span class="hop-t">{_e(ev["title"])}</span>'
                + (f' <span class="hop-l">{_e(refs)}</span>' if refs else "")
                + "</div>")
        body = ""
        if ev.get("code"):
            body = (code_block_html(ev["code"], ev.get("lines", []), cls)
                    if ev["kind"] in ("sql", "formula")
                    else f'<div class="map">{_e(ev["code"])}</div>')
        if ev.get("note"):
            body += f'<div class="note">{_e(ev["note"])}</div>'
        parts.append(f'<div class="ev">{head}{body}</div>')
    return "".join(parts)


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def results_csv(results: List[ImpactResult],
                assessment: Optional[ImpactAssessment] = None) -> str:
    cdes_by_id: Dict[str, List[str]] = {}
    critical = set()
    if assessment:
        rc = assessment.layers["reporting_components"]
        for item in (rc["semantic"] + rc["calculations"] + rc["worksheets"]
                     + assessment.layers["business_reports"]):
            cdes_by_id[item["id"]] = item.get("cdes", [])
        critical = {r["id"] for r in assessment.critical_reports}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["severity", "system", "asset_type", "asset_name", "asset_id", "cdes",
                "critical_report", "logic_locations", "path"])
    for r in results:
        w.writerow([r.severity.value, r.system.value, r.asset_type.value, r.asset_name,
                    r.asset_id, "; ".join(cdes_by_id.get(r.asset_id, [])),
                    "yes" if r.asset_id in critical else "", evidence_locations(r),
                    r.reason])
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# HTML template
# --------------------------------------------------------------------------- #
_CSS = """
@page { size: A4; margin: 15mm 14mm 16mm 14mm;
  @bottom-left { content: string(doc-title); font: 7pt Helvetica, Arial, sans-serif;
                 color: #80868d; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages);
                  font: 7pt Helvetica, Arial, sans-serif; color: #80868d; } }
body { font-family: Helvetica, Arial, sans-serif; font-size: 9pt; line-height: 1.4;
  color: #3f444b; margin: 0; }
h1 { font-size: 19pt; color: #111214; margin: 0 0 2pt 0; string-set: doc-title content(); }
h2 { font-size: 8pt; color: #80868d; letter-spacing: 1pt; text-transform: uppercase;
  margin: 14pt 0 6pt 0; padding-bottom: 3pt; border-bottom: 0.5pt solid #dcdcd8;
  page-break-after: avoid; -pdf-keep-with-next: true; }
p { margin: 0 0 4pt 0; }
.sub { color: #80868d; font-size: 8pt; margin-bottom: 8pt; }
.mono, .path, .map, table.code td { font-family: "Courier New", Courier, monospace; }
b, strong { color: #111214; }

table { border-collapse: collapse; width: 100%; }
td { vertical-align: top; }
.box td { border: 0.5pt solid #dcdcd8; padding: 5pt 7pt; }
.soft { background-color: #f5f5f3; }
.k { font-size: 6.5pt; letter-spacing: 1pt; text-transform: uppercase; color: #80868d; }
.banner td { background-color: #f5f5f3; border: 0.5pt solid #dcdcd8; padding: 6pt 8pt;
  vertical-align: middle; }
.big { font-size: 19pt; font-weight: bold; color: #111214; }
.rating { font-weight: bold; letter-spacing: 1pt; text-transform: uppercase; }
.high { color: #c63b3b; } .medium { color: #b8730f; } .low { color: #3f7f1a; }
.cde { color: #2f6fd1; } .crit { color: #c63b3b; }
.flagged { color: #c63b3b; font-size: 6.5pt; font-weight: bold; }
.clear { color: #3f7f1a; font-size: 6.5pt; font-weight: bold; }

.flow td.col { width: 25%; padding: 0 3pt; }
.flow td.hd { font-size: 6.5pt; letter-spacing: 1pt; text-transform: uppercase;
  color: #80868d; padding: 0 3pt 3pt 3pt; font-weight: bold; }
/* Cards are one-cell tables with single class names: every engine (incl.
   xhtml2pdf) draws one box per card that way. */
table.card, table.cardcrit, table.cardcde { margin-bottom: 4pt; }
table.card td, table.cardcrit td, table.cardcde td { padding: 4pt 6pt; font-size: 7.5pt; }
table.card td { border: 0.5pt solid #dcdcd8; background-color: #f5f5f3; }
table.cardcde td { border: 0.5pt solid #2f6fd1; background-color: #f5f5f3; }
table.cardcrit td { border: 0.5pt solid #111214; background-color: #111214; color: #ffffff; }
.ct { font-weight: bold; color: #111214; font-size: 9pt; }
table.cardcrit .ct { color: #ffffff; }

.item { page-break-inside: avoid; margin-bottom: 7pt; }
.tname { font-weight: bold; color: #111214; font-size: 9.5pt; }
hr.sep { border: 0; border-top: 0.5pt solid #dcdcd8; height: 0; margin: 8pt 0 4pt 0; }
.aname { font-weight: bold; color: #111214; font-size: 10.5pt; }
.sev { font-size: 7pt; font-weight: bold; letter-spacing: 0.5pt; }
.sev.breaking { color: #c63b3b; } .sev.warning { color: #b8730f; } .sev.info { color: #2f6fd1; }
.tags { font-size: 7pt; letter-spacing: 0.4pt; text-transform: uppercase; color: #3f444b; }
.path { font-size: 7pt; color: #80868d; margin: 2pt 0 3pt 0; }
.ev { page-break-inside: avoid; }
.hop { font-size: 8pt; color: #111214; margin: 5pt 0 2pt 0; }
.hop-n { color: #80868d; }
.hop-t { font-weight: bold; }
.hop-l, .refs { font-family: "Courier New", Courier, monospace; color: #b8730f; }
.map { font-size: 7.5pt; background-color: #fbfbfa; border: 0.5pt solid #dcdcd8;
  padding: 3pt 6pt; }
.note { font-size: 7pt; color: #80868d; }

table.code { border: 0.5pt solid #dcdcd8; background-color: #fbfbfa; }
table.code td { font-size: 7.2pt; line-height: 1.3; padding: 0.5pt 5pt; color: #111214; }
table.code td.ln { width: 22pt; text-align: right; color: #80868d;
  border-right: 0.5pt solid #dcdcd8; }
table.code tr.hit td { background-color: #fff1cc; }
table.code tr.hit td.ln { color: #111214; font-weight: bold;
  border-left: 2.5pt solid #e0a526; }
.foot { font-size: 7pt; color: #80868d; margin-top: 10pt; }
"""


def _card(title: str, sub: str = "", cls: str = "card") -> str:
    return (f'<table class="{cls}"><tr><td><span class="ct">{_e(title)}</span>'
            + (f"<br/>{_e(sub)}" if sub else "") + "</td></tr></table>")


def _names(items: List[Dict[str, Any]]) -> str:
    return ", ".join(i.get("label") or i["name"] for i in items)


def report_html(change: ChangeRequest, results: List[ImpactResult],
                assessment: ImpactAssessment,
                generated_at: Optional[datetime] = None) -> str:
    a = assessment
    when = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M UTC")
    rating = a.rating.value
    obj = change.target_node_id.split(":")[-1]
    k, L = a.kpis, a.layers
    rc = L["reporting_components"]

    # -- header + KPIs ---------------------------------------------------------
    src_cdes = "".join(f' &nbsp;<span class="cde">CDE: {_e(c["name"])}</span>'
                       for c in a.source_cdes)
    banner = (
        '<table class="banner"><tr>'
        f'<td><span class="k">Selected change</span><br/>'
        f'<b>{_e(change.change_type.value.upper())} {_e(obj.split(".")[-1].upper())}</b>'
        f' &nbsp;<span class="mono">{_e(obj)}</span>{src_cdes}</td>'
        f'<td style="width:24%;text-align:right"><span class="rating {rating}">'
        f"{rating} impact</span></td></tr></table>"
    )
    kpis = [
        (k["cdes"], "Critical data elements",
         " + ".join(c["name"] for c in a.cdes) or "No CDEs touched"),
        (k["downstream_tables"], "Downstream tables",
         "Tables affected by the field change" if k["downstream_tables"]
         else "No tables derive from the field"),
        (k["core_tables"], "Core tables",
         f"Included in the {k['downstream_tables']} downstream tables"
         if k["downstream_tables"] else "No downstream tables"),
        (k["critical_reports"], "Critical reports",
         ", ".join(r["name"] for r in a.critical_reports) or "None classified critical"),
    ]
    kpi_html = ('<table class="box" style="margin-top:5pt"><tr>' + "".join(
        f'<td style="width:25%"><span class="big">{n}</span><br/><b>{_e(t)}</b><br/>'
        f'<span style="font-size:7.5pt">{_e(s)}</span></td>' for n, t, s in kpis)
        + "</tr></table>")

    # -- assessment ------------------------------------------------------------
    dims = "".join(
        f'<tr><td style="width:28%"><b>{_e(d["name"])}</b><br/>'
        f'<span class="{"flagged" if d["flagged"] else "clear"}">'
        f'{"FLAGGED" if d["flagged"] else "CLEAR"}</span></td>'
        f'<td>{_e(d["detail"])}</td></tr>'
        for d in a.dimensions
    )
    assessment_html = (
        f'<table class="box"><tr><td style="width:28%"><span class="rating {rating}">'
        f'{rating} impact</span></td><td>Rule-based governance assessment</td></tr>'
        f"{dims}</table>"
        f'<p style="margin-top:5pt"><b>Review focus:</b> {_e(a.review_focus)}</p>'
        + (f'<p><b>Consult:</b> {_e("; ".join(a.owners))}</p>' if a.owners else "")
    )

    # -- downstream flow -------------------------------------------------------
    core, derived = L["data_products"]["core"], L["data_products"]["derived"]
    src = L["source"]
    col_src = _card(src["name"], "CDE: " + ", ".join(src["cdes"]) if src["cdes"]
                    else "Not a governed CDE")
    col_dp = ((_card(f"{len(core)} core tables", _names(core)) if core else "")
              + (_card(f"{len(derived)} derived tables", _names(derived)) if derived
                 else "")) or _card("No downstream tables")
    rest = [c for c in rc["calculations"] if not c["cdes"]] + rc["worksheets"]
    col_rc = ((_card("Views and semantic fields", _names(rc["semantic"]))
               if rc["semantic"] else "")
              + "".join(_card(", ".join(c["cdes"]), f"Affected CDE calculation: {c['name']}",
                              "cardcde") for c in rc["calculations"] if c["cdes"])
              + (_card("Worksheets and calculations", _names(rest)) if rest else "")
              ) or _card("No reporting components")
    col_br = "".join(
        _card(r["name"], ("Critical report · " + r["owner"]) if r["criticality"] == "critical"
              else "Standard report", "cardcrit" if r["criticality"] == "critical" else "card")
        for r in sorted(L["business_reports"], key=lambda r: r["criticality"] != "critical")
    ) or _card("No business reports")
    heads = ["Source field", "Data products", "Reporting components", "Business report"]
    flow = ('<table class="flow"><tr>'
            + "".join(f'<td class="hd">{h}</td>' for h in heads) + "</tr><tr>"
            + "".join(f'<td class="col">{c}</td>' for c in (col_src, col_dp, col_rc, col_br))
            + "</tr></table>")

    # -- data product logic ----------------------------------------------------
    table_logic = "".join(
        f'<div class="item"><span class="tname">{_e(t["label"])}</span> '
        f'<span class="k">{_e(t["tier"])}</span> '
        f'<span class="path">{_e(t["name"])} · lines reading the changed field: </span>'
        f'<span class="refs">{_e(line_refs(t["logic"]["lines"]) or "none")}</span>'
        f'{code_block_html(t["logic"]["code"], t["logic"]["lines"])}</div>'
        for t in a.downstream_tables if t.get("logic")
    )

    # -- impacted assets -------------------------------------------------------
    cdes_by_id = {i["id"]: i.get("cdes", []) for i in
                  rc["semantic"] + rc["calculations"] + rc["worksheets"]
                  + L["business_reports"]}
    critical = {r["id"] for r in a.critical_reports}
    assets = ""
    for r in results:
        tags = [_e(r.system.value), _e(r.asset_type.value.replace("_", " "))]
        tags += [f'<span class="cde">CDE · {_e(c)}</span>'
                 for c in cdes_by_id.get(r.asset_id, [])]
        if r.asset_id in critical:
            tags.append('<span class="crit">Critical report</span>')
        hops = [evidence_html([ev]).replace('class="hop-n">1<', f'class="hop-n">{i}<', 1)
                for i, ev in enumerate(r.evidence, 1)]
        # The header travels with its first hop so it never strands at a page end.
        assets += (
            '<hr class="sep"/><div class="item">'
            f'<span class="sev {r.severity.value}">{r.severity.value.upper()}</span> '
            f'<span class="aname">{_e(r.asset_name)}</span>'
            f'<div class="tags">{" · ".join(tags)}</div>'
            f'<div class="path">{_e(r.reason)}</div>{hops[0] if hops else ""}</div>'
            + "".join(hops[1:])
        )
    if not assets:
        assets = "<p>No view, query or Tableau asset reads this object.</p>"

    prov = ", ".join(f"{a.provenance[s]} {label}" for s, label in PROVENANCE_LABEL.items()
                     if a.provenance.get(s))
    title = f"Change Impact Report — {change.change_type.value} {obj}"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style></head>
<body>
<h1>Change Impact Report</h1>
<p class="sub">Generated {_e(when)} · deterministic dependency-graph analysis ·
{_e(change.change_type.value)} {_e(obj)} · {rating} impact</p>
{banner}
{kpi_html}

<h2>Impact assessment</h2>
{assessment_html}

<h2>Downstream impact</h2>
{flow}

{f"<h2>Data product logic</h2>{table_logic}" if table_logic else ""}

<h2>Impacted assets ({len(results)}) with calculation logic</h2>
{assets}

<p class="foot">Line numbers refer to the view / query / table definition shown; highlighted
lines reference the changed field. Core tables are a subset of downstream tables; a CDE may
span multiple assets. Classifications come from the governance overlay, then Unity Catalog
tags, then lineage inference{(" (" + _e(prov) + ")") if prov else ""}.</p>
</body></html>
"""
