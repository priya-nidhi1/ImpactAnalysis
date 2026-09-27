# Change Impact Analysis — Prototype

AI-powered **change impact analysis** that predicts the downstream blast radius of a
Databricks schema change **before deployment** — across Databricks SQL/views **and**
Tableau dashboards, data sources, and calculated fields.

> Ask *"What breaks if I rename `policy_status`?"* and get a graded, explainable
> impact report instead of finding out from a broken dashboard after release.

**📖 Docs & interactive demo:** <https://priya-nidhi1.github.io/ImpactAnalysis/> —
a static site (MkDocs Material + a precomputed demo of the real engine) deployed
from `main` by [`.github/workflows/pages.yml`](.github/workflows/pages.yml). Build it
locally with `pip install mkdocs-material`, then
`python scripts/export_demo_data.py && mkdocs serve`.

## Why this is trustworthy

The **deterministic graph engine is the source of truth**:

- **SQL impact** comes from real column-level parsing with `sqlglot` (alias-aware,
  `*`-expanding) — not just query-history lineage.
- **Tableau impact** comes from the Metadata API field→column graph, bridged to
  Databricks columns by fully-qualified name.

The **Mosaic AI** layer only *phrases* the results and *extracts intent* from chat
questions — it never invents a dependency. With no model endpoint configured, the
prototype runs fully offline with deterministic summaries.

On the labeled sample fixtures the engine scores **precision 1.00 / recall 1.00**.

## Architecture

```
connectors (sample | live)
   ├─ Databricks: information_schema + system.* + sqlglot SQL parsing
   └─ Tableau:    Metadata API (GraphQL)
        ↓ extract → unified nodes + edges (the "dependency repository", Delta/JSON)
        ↓ networkx DiGraph  (Databricks ↔ Tableau joined at `maps_to` bridges)
        ↓ impact engine  (downstream BFS + severity + explanation path)
        ↓ Mosaic AI summary / NL chat
        ↓ Streamlit Databricks App  (Propose Change + Chat)
```

Edges always point **producer → consumer**, so impact analysis is a reachability
walk from the changed node. See [`src/impact/model.py`](src/impact/model.py).

## Layout

| Path | What |
|------|------|
| [`src/impact/`](src/impact) | the engine (model, connectors, extract, graph, governance, ai, store, pipeline) |
| [`fixtures/`](fixtures) | synthetic insurance "policy" metadata + labeled expected impact |
| [`fixtures/governance/catalog.json`](fixtures/governance/catalog.json) | governance overlay: CDEs, table tiers, critical reports, rating rules |
| [`notebooks/`](notebooks) | Databricks notebooks `00`→`40` |
| [`app/`](app) | Streamlit Databricks App |
| [`scripts/validate.py`](scripts/validate.py) | precision/recall harness |
| [`tests/`](tests) | sqlglot + impact-engine + governance tests |

## Run it locally (sample mode, no credentials)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                       # 1. unit + end-to-end tests
python scripts/validate.py      # 2. precision/recall on labeled fixtures
streamlit run app/app_revamped.py  # 3. the UI (Propose Change + Chat)
```

## Governance: critical data elements and impact rating

Every change is also rolled up into a governance view, so you can trace a field
change through data products to critical business reporting
([`src/impact/governance/`](src/impact/governance)):

| Output | How it is derived |
|---|---|
| **Critical data elements** | CDEs bound to the changed field or to anything downstream of it. A CDE is a business concept (e.g. *Policy status*) that can span many physical assets. |
| **Downstream tables** | Distinct tables whose columns derive from the field (`column_lineage` → `derives_from` edges), excluding the source table. |
| **Core tables** | The downstream tables tagged `core`. The rest are *derived*. |
| **Critical reports** | Reached dashboards classified `critical`. |
| **Layered flow** | Source field → data products (core / derived) → reporting components (views & semantic fields, CDE calculations, worksheets) → business reports. |
| **Impact rating** | **High**: the change is breaking and ≥ 2 dimensions are flagged, or it is breaking and reaches a critical report, or all three dimensions are flagged. **Medium**: any dimension is flagged, or the change is breaking. **Low**: otherwise. The three dimensions are *CDE criticality*, *Core data dependency* and *Critical reporting*. Thresholds live in the overlay's `rules` block. |
| **Review focus** | Confirm CDE mappings and ownership / validate dependency paths / test affected reporting logic, plus the owners and stewards to consult. |

Classifications resolve in this order: **1. governance overlay** (`governance.overlay`
in `config/settings.yaml`, versioned with the code), then **2. Unity Catalog tags** on
tables and columns (`cde=<CDE name>`, `data_tier=core|derived`,
`criticality=critical`, `data_owner=<owner>`; read from
`information_schema.table_tags` / `column_tags` in live mode), then **3. inference**:
a table with inbound column lineage is `derived`. The UI footnote reports how many
classifications came from each source.

### Line numbers, calculation logic and reports

Every impacted asset carries a hop-by-hop **evidence trail**
([`src/impact/evidence.py`](src/impact/evidence.py)). Each hop shows the view or query
SQL, the derived table's definition (the optional `definition` on a table in the raw
metadata) or the Tableau formula, with the **line numbers that reference the changed
field** highlighted. Line numbers come from sqlglot token positions, resolved through
table aliases. In the app, open **Calculation logic** on any asset row or table under
**Data product logic**.

**Download report** (below the KPI tiles) offers two files
([`src/impact/report.py`](src/impact/report.py)):
- **PDF**: the rating, KPIs, flow, data-product logic and every asset's line-numbered
  code with the referencing lines highlighted. It is an HTML template rendered by
  **WeasyPrint**, falling back to pure-Python **xhtml2pdf** where WeasyPrint's Pango
  system library is missing (e.g. a minimal container). Force one with
  `IMPACT_PDF_ENGINE=weasyprint|xhtml2pdf`
  ([`src/impact/report_pdf.py`](src/impact/report_pdf.py));
- **CSV**: one row per asset, with CDEs, critical-report flag and line locations.

In the sample fixtures, renaming `policies.policy_status` touches **2 CDEs** (*Policy
status*, *Renewal eligibility*) and **8 downstream tables**, **2 of them core** (*Policy
master*, *Policy term*). It reaches **1 critical report** (*Executive Policy Dashboard*)
and is rated **High impact**. `scripts/validate.py` checks these roll-ups against
`expected_governance` in [`fixtures/expected_impact.json`](fixtures/expected_impact.json).

## Run it in Databricks (live mode)

1. Run [`notebooks/00_setup_catalog.py`](notebooks/00_setup_catalog.py) to create the
   `impact_analysis` schema + fixtures volume and store the Tableau PAT in a secret scope.
2. Set `mode: live` in [`config/settings.yaml`](config/settings.yaml) (or `IMPACT_MODE=live`)
   and fill in your catalog/schema, Tableau server/site, and Mosaic AI endpoint.
3. Run notebooks `10` → `20` → `30` → `40`, or deploy the app with
   [`app/app.yaml`](app/app.yaml). Same code path, real metadata.

## Leadership demo script (≈3 min)

1. **Frame it:** "A developer wants to rename `policy_status`. Today they trace impact
   by hand for hours and still miss Tableau." Open the app (Mode badge shows asset/dependency counts).
2. **Chat tab:** type *"What will be impacted if I rename policy_status?"* → it interprets
   the change and returns **11 breaking assets** spanning **3 Databricks** objects and
   **8 Tableau** objects, each with a *why* path
   (`policies.policy_status → Policy Status → Status Breakdown → Executive Policy Dashboard`).
3. **Governance:** the same result opens with a **High impact** rating: **2 CDEs**, **8
   downstream tables (2 core)** and **1 critical report**, laid out as source field →
   data products → reporting components → Executive Policy Dashboard, with a review focus.
4. **Contrast:** pick `premium_amount` + **retype** → a smaller **warning** set — the engine
   distinguishes breaking from non-breaking changes.
5. **Credibility:** `python scripts/validate.py` → **precision 1.00 / recall 1.00** on the
   labeled set. Time-to-analysis: **< 5 minutes vs 2–6 hours** manual.
6. **Close:** same engine runs live in Databricks; AI summary is additive on top of an
   auditable deterministic core.

## Scope (v1) and what's next

**In:** Databricks SQL/views + Tableau dashboards/data sources/calculated fields; sample +
live connectors; Mosaic AI summary/chat with offline fallback.

**Deferred:** notebook scanning, Git/dbt scanning, CI/CD deployment gate, vector search,
autonomous agents, continuous extraction.
