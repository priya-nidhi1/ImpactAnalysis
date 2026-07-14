# Change Impact Analysis — Prototype

AI-powered **change impact analysis** that predicts the downstream blast radius of a
Databricks schema change **before deployment** — across Databricks SQL/views **and**
Tableau dashboards, data sources, and calculated fields.

> Ask *"What breaks if I rename `policy_status`?"* and get a graded, explainable
> impact report instead of finding out from a broken dashboard after release.

**📖 Docs & interactive demo:** <https://priya-nidhi1.github.io/Impact_Analysis/> —
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
| [`src/impact/`](src/impact) | the engine (model, connectors, extract, graph, ai, store, pipeline) |
| [`fixtures/`](fixtures) | synthetic insurance "policy" metadata + labeled expected impact |
| [`notebooks/`](notebooks) | Databricks notebooks `00`→`40` |
| [`app/`](app) | Streamlit Databricks App |
| [`scripts/validate.py`](scripts/validate.py) | precision/recall harness |
| [`tests/`](tests) | sqlglot + impact-engine tests |

## Run it locally (sample mode, no credentials)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                       # 1. unit + end-to-end tests
python scripts/validate.py      # 2. precision/recall on labeled fixtures
streamlit run app/app.py        # 3. the UI (Propose Change + Chat tabs)
```

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
   the change and returns **8 breaking assets** spanning **3 Databricks** objects and
   **5 Tableau** objects, each with a *why* path
   (`policies.policy_status → Policy Status → Status Breakdown → Executive Policy Dashboard`).
3. **Contrast:** pick `premium_amount` + **retype** → a smaller **warning** set — the engine
   distinguishes breaking from non-breaking changes.
4. **Credibility:** `python scripts/validate.py` → **precision 1.00 / recall 1.00** on the
   labeled set. Time-to-analysis: **< 5 minutes vs 2–6 hours** manual.
5. **Close:** same engine runs live in Databricks; AI summary is additive on top of an
   auditable deterministic core.

## Scope (v1) and what's next

**In:** Databricks SQL/views + Tableau dashboards/data sources/calculated fields; sample +
live connectors; Mosaic AI summary/chat with offline fallback.

**Deferred:** notebook scanning, Git/dbt scanning, CI/CD deployment gate, vector search,
autonomous agents, continuous extraction.
