# Plan: AI-Powered Change Impact Analysis — Working Prototype

## Context

**Problem.** Data Engineering makes schema changes (add / drop / rename / retype columns) in
Databricks regularly. Databricks gives table-level lineage, but nobody can see how a change
ripples into **downstream SQL/views** and **Tableau dashboards, data sources, and calculated
fields**. Today impacts are found *after* deployment — broken dashboards, incidents, root-cause
hunts, delayed releases. The process is reactive.

**Goal of this prototype.** A *serious working prototype* that, given a proposed schema change
(e.g. "rename `policy_status`"), produces — **before deployment** — a concrete, trustworthy
impact report listing the affected Databricks SQL/views and Tableau assets, plus a natural-language
summary and remediation hints. The headline demo: *"What breaks if I rename `policy_status`?"* →
impacted views + Tableau data sources, calculated fields, and dashboards.

**Locked decisions (from scoping):**
- **Platform/stack:** Databricks-native — notebooks + a Python package; metadata stored as Delta
  tables in Unity Catalog; UI as a **Databricks App (Streamlit)**.
- **Data access:** Build **real connectors** *and* ship a **sample-fixture fallback** so the demo
  always runs without live credentials (de-risks credential/access delays).
- **LLM:** **Databricks Mosaic AI** Foundation Model serving endpoint (thin summary/NL layer only).
- **v1 downstream coverage:** **Databricks SQL / views** + **Tableau dashboards & data sources**
  (incl. calculated fields). **Out of scope for v1:** notebook scanning, Git/dbt scanning,
  CI/CD gate, vector search, autonomous agents, continuous/real-time extraction.

**Design principle (why this is "serious," not a toy):** the **deterministic graph engine is the
source of truth**. SQL impact comes from real column-level parsing (`sqlglot`); Tableau impact
comes from the Metadata API field→column graph. The LLM only *phrases* results and *extracts intent*
from chat — it never invents dependencies. This keeps results auditable.

---

## Target Repo Layout (greenfield, under `/Users/priyank/Desktop/RnD/Impact_Analysis`)

```
Impact_Analysis/
  README.md
  requirements.txt              # sqlglot, networkx, tableauserverclient, databricks-sdk, pyyaml,
                                # streamlit, pyvis, pytest
  config/settings.yaml          # catalogs/schemas, tableau site, model endpoint, mode: live|sample
  src/impact/
    config.py
    model.py                    # Node, Edge, ChangeRequest, ImpactResult + NodeType/EdgeType enums
    connectors/{base.py, databricks_live.py, tableau_live.py, sample.py}
    extract/{databricks_meta.py, sql_lineage.py, tableau_meta.py}
    graph/{build.py, impact.py}
    ai/{summarize.py, nl_change.py}
    store/delta.py              # read/write nodes, edges, change_requests, impact_results
  notebooks/{00_setup_catalog, 10_extract_databricks, 20_extract_tableau,
             30_build_graph, 40_impact_demo}.py
  app/{app.py, app.yaml}        # Databricks App: "Propose Change" + "Chat" tabs
  fixtures/{databricks/, tableau/}   # realistic synthetic metadata (insurance "policy" domain)
  tests/{test_sql_lineage.py, test_impact.py}
```

**Unified graph model** (the "dependency repository", stored as Delta `nodes` / `edges`):
- **Node types:** `catalog`, `schema`, `table`, `view`, `column`, `tableau_datasource`,
  `tableau_field`, `tableau_calc_field`, `tableau_worksheet`, `tableau_dashboard`, `query`.
- **Edge types:** `contains` (table→column), `derives_from` (column→column lineage),
  `references` (query/view→column), `maps_to` (tableau_field→databricks column — the cross-system
  bridge), `computed_from` (calc_field→field), `used_in` (field→worksheet→dashboard).
- Tables: `nodes`, `edges`, `change_requests`, `impact_results`.

---

## Action Items (sequenced, ~4–6 weeks, 1 Data Engineer + 1 BI/Data Architect)

### Milestone 0 — Foundations & scaffolding  *(Week 1)*
- [ ] Create UC catalog/schema `impact_analysis` for metadata tables + a UC **Volume** for fixtures.
- [ ] Stand up repo layout above as a **Databricks Git folder / Repo**; package `src/impact` (install via `%pip install -e` or wheel).
- [ ] Secrets: Databricks **secret scope** for Tableau PAT + site/host; `settings.yaml` holds target catalogs/schemas, Tableau site, model endpoint name, and `mode: live|sample`.
- [ ] Define `model.py` (Node/Edge/ChangeRequest/ImpactResult dataclasses + enums) and `store/delta.py` (CRUD on the 4 Delta tables).
- [ ] Author **sample fixtures** for a realistic *insurance "policy"* domain that includes the `policy_status` column referenced by views + Tableau (so the headline demo is reproducible offline).
- [ ] `connectors/base.py`: `Connector` ABC with `get_databricks_metadata()` / `get_tableau_metadata()`; `sample.py` loads fixtures; live connectors stubbed.

### Milestone 1 — Databricks metadata extraction  *(Week 1–2)*
- [ ] `extract/databricks_meta.py`: pull `information_schema.tables` / `.columns` for target schema(s) → `table`/`column` nodes + `contains` edges.
- [ ] Pull `system.access.table_lineage` + `system.access.column_lineage` → `derives_from` edges (table & column lineage from query history).
- [ ] `extract/sql_lineage.py`: fetch **view definitions** (`information_schema.views`) and recent `system.query.history` SQL; parse with **`sqlglot`** for **column-level references** → `query`/`view` nodes + `references` edges. *(This is what makes SQL impact real, not just query-history-derived.)*
- [ ] Notebook `10_extract_databricks` orchestrates the above; persist to Delta; verify sample-mode path.

### Milestone 2 — Tableau metadata extraction + cross-system bridge  *(Week 2–3)*
- [ ] `extract/tableau_meta.py`: **Tableau Metadata API (GraphQL)** client (`tableauserverclient` + raw GraphQL). Extract data sources, `databaseTables`/`databaseColumns` (`upstreamColumns`/`upstreamTables`), workbooks, worksheets, dashboards, fields, **calculatedFields (with formula)**.
- [ ] Build the **bridge**: map Tableau `databaseColumn` → Databricks `column` by fully-qualified name (`catalog.schema.table.column`) → `maps_to` edges. This is the link that turns "DB change → Tableau impact" into a graph walk.
- [ ] Parse calculated-field **formulas** for referenced field names → `computed_from` edges. Build `field → worksheet → dashboard` `used_in` edges.
- [ ] Notebook `20_extract_tableau`; persist; verify sample-mode path.
- [ ] **Risk note:** full Tableau upstream-column lineage needs Tableau Catalog/Data Management. Fallback: parse published-datasource XML (`.tdsx`) for column refs — fixtures cover the demo regardless.

### Milestone 3 — Dependency graph + impact engine  *(Week 3–4)*
- [ ] `graph/build.py`: load Delta `edges` into a **`networkx` DiGraph**; run column identity resolution to merge the Databricks + Tableau subgraphs at `maps_to` bridges.
- [ ] `graph/impact.py`: `ChangeRequest` supports **add / drop / rename / datatype-change / logic-change** on a column or table. Downstream BFS from the changed node collects impacted assets **with the path** (the "why").
- [ ] **Severity rules:** drop/rename of a referenced column → `BREAKING`; datatype change → `WARNING`; add → `INFO`; calc-field referencing a renamed/dropped field → `BREAKING`; dashboard transitively using a broken field → `BREAKING`. Output rows: `{asset, type, system, severity, path/reason}` into `impact_results`.
- [ ] `tests/test_impact.py` + `tests/test_sql_lineage.py`: unit-test traversal & sqlglot parsing against fixtures.

### Milestone 4 — Mosaic AI summary + NL chat  *(Week 4–5)*
- [ ] `ai/summarize.py`: prompt template `structured impact_results → executive summary + remediation hints`; call the **Mosaic AI Foundation Model serving endpoint**.
- [ ] `ai/nl_change.py`: LLM extracts `{target object, change type}` from NL (e.g. *"rename policy_status"*) as JSON → feeds the **deterministic** engine. LLM never sources dependencies.

### Milestone 5 — Databricks App UI  *(Week 5)*
- [ ] `app/app.py` (**Streamlit Databricks App**), two tabs:
  - **Propose Change:** pick catalog/schema/table/column + change type → grouped impact report (by system & severity) + dependency-graph viz (`pyvis`/node-link) + AI summary.
  - **Chat:** free-text question → `nl_change` → engine → `summarize`.
- [ ] `app/app.yaml` deploy config; wire to Delta tables + model endpoint.

### Milestone 6 — Demo, validation & docs  *(Week 6)*
- [ ] **End-to-end demo:** rename `policy_status` → show impacted Databricks views + Tableau data sources/calculated fields/dashboards + AI summary, live in the app.
- [ ] **Accuracy validation:** hand-label known dependencies in the fixture set; measure **precision/recall** of impact detection (credibility metric for leadership).
- [ ] **Metrics for the pitch:** time-to-impact-analysis (target <5 min vs 2–6 hrs today).
- [ ] `README.md` runbook (setup, sample vs live mode, run order) + a short **leadership demo script**.

---

## Verification

1. **Unit tests (offline, no creds):** `pytest tests/` — confirms `sqlglot` column extraction and
   graph traversal/severity against fixtures.
2. **Pipeline smoke (sample mode):** run notebooks `00 → 10 → 20 → 30` with `mode: sample`; confirm
   `nodes`/`edges` Delta tables populate and the Databricks + Tableau subgraphs join at `maps_to`.
3. **Headline scenario:** run `40_impact_demo` (and the app's Propose-Change tab) for
   `rename policy_status` → assert the expected impacted views, Tableau data sources, calculated
   fields, and dashboards appear with correct severities and a coherent AI summary.
4. **Chat path:** ask *"What breaks if I rename policy_status?"* in the Chat tab → same impacted set
   as #3 (proves NL extraction routes into the deterministic engine).
5. **Accuracy:** report precision/recall vs the hand-labeled fixture dependencies.
6. **Live switch (if creds land):** flip `mode: live`, re-run extraction against a real
   schema/Tableau site, confirm parity of behavior.

## Key risks / watch-items
- **Databricks column lineage** (`system.access.column_lineage`) is query-history-derived and can be
  incomplete → mitigated by `sqlglot` view/query parsing.
- **Tableau upstream-column lineage** needs Tableau Catalog enabled → fallback to `.tdsx` XML parsing;
  fixtures keep the demo independent of this.
- **Mosaic AI endpoint** availability → confirm a pay-per-token Foundation Model endpoint exists; the
  deterministic engine works without it, so AI is additive, not blocking.
