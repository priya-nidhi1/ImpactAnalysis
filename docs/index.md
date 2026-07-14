# Change Impact Analysis

AI-powered **change impact analysis** that predicts the downstream blast radius of a
Databricks schema change **before deployment** — across Databricks SQL/views **and**
Tableau dashboards, data sources, and calculated fields.

> Ask *"What breaks if I rename `policy_status`?"* and get a graded, explainable
> impact report instead of finding out from a broken dashboard after release.

[:material-play-circle: Try the live demo](demo.md){ .md-button .md-button--primary }
[:material-sitemap: Read the architecture](ARCHITECTURE.md){ .md-button }

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

## How it works

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
walk from the changed node. See the [Architecture](ARCHITECTURE.md) page for the
full data model, extraction pipeline, and severity rules.

## Run it locally (sample mode, no credentials)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                       # 1. unit + end-to-end tests
python scripts/validate.py      # 2. precision/recall on labeled fixtures
streamlit run app/app.py        # 3. the UI (Propose Change + Chat tabs)
```

## Run it in Databricks (live mode)

1. Run `notebooks/00_setup_catalog.py` to create the `impact_analysis` schema +
   fixtures volume and store the Tableau PAT in a secret scope.
2. Set `mode: live` in `config/settings.yaml` (or `IMPACT_MODE=live`) and fill in
   your catalog/schema, Tableau server/site, and Mosaic AI endpoint.
3. Run notebooks `10` → `20` → `30` → `40`, or deploy the app with `app/app.yaml`.
   Same code path, real metadata. See the
   [Dashboard & Integration guide](DASHBOARD.md) for the wiring checklist.

## Scope (v1) and what's next

**In:** Databricks SQL/views + Tableau dashboards/data sources/calculated fields;
sample + live connectors; Mosaic AI summary/chat with offline fallback.

**Deferred:** notebook scanning, Git/dbt scanning, CI/CD deployment gate, vector
search, autonomous agents, continuous extraction. The road map is in the
[Prototype Plan](prototype-plan.md).
