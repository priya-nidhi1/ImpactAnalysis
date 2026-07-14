# Dashboard & Integration Guide

How the impact engine connects to a dashboard — both the built-in Streamlit app
and any external BI dashboard (Databricks AI/BI, Tableau) that reads the results.

## The built-in dashboard (`app/app.py`)

A **Streamlit Databricks App** with three tabs:

| Tab | What it does | Engine calls |
|-----|--------------|--------------|
| **Propose Change** | pick a column + change type → graded impact report (Breaking/Warning metrics, asset table, AI summary) | `analyze_change` → `summarize_impact` |
| **Chat** | ask in natural language ("what breaks if I rename policy_status?") | `parse_nl_change` → `analyze_change` → `summarize_impact` |
| **Docs** | renders this documentation in-app so it travels with the dashboard | reads `docs/*.md` |

The graph is built once and cached (`@st.cache_resource` → `build_graph_in_memory`).
The mode badge shows `mode`, asset count, and dependency count.

### Run
```bash
streamlit run app/app.py               # local, sample mode
# or deploy with app/app.yaml as a Databricks App (set IMPACT_MODE=live)
```

## The data contract (how any dashboard connects)

Every dashboard consumes the **same `ImpactResult` records** the engine produces.
One row per impacted asset:

| Field | Type | Notes |
|-------|------|-------|
| `asset_id` | string | canonical node id (e.g. `tab:dashboard:Executive Policy Dashboard`) |
| `asset_name` | string | display name |
| `asset_type` | enum | `view` \| `query` \| `tableau_field` \| `tableau_calc_field` \| `tableau_worksheet` \| `tableau_dashboard` |
| `system` | enum | `databricks` \| `tableau` |
| `severity` | enum | `breaking` \| `warning` \| `info` |
| `reason` | string | human-readable dependency path (`A --referenced by--> B --used in--> C`) |
| `path` | string[] | the same path as tokens, for custom rendering |

Two integration patterns:

### 1. In-process (Streamlit / notebooks)
Call the engine directly and render the returned list:

```python
from impact.config import load_settings
from impact.pipeline import build_graph_in_memory, analyze
from impact.model import ChangeRequest, ChangeType

settings = load_settings()
graph = build_graph_in_memory(settings)
results = analyze(
    ChangeRequest("db:column:insurance.policy.policies.policy_status", ChangeType.RENAME),
    settings, graph=graph, persist=True,     # persist=True also writes to the store
)
for r in results:
    print(r.severity.value, r.system.value, r.asset_name, "—", r.reason)
```

### 2. Out-of-process (external BI dashboard)
Run analysis with `persist=True` (or the `40_impact_demo` notebook) so results land
in the store, then point a Databricks AI/BI dashboard or a Tableau extract at the
`impact_results` table:

- **Live (Delta):** `{catalog}.{metadata_schema}.impact_results`. In the prototype
  each row is a JSON `payload` string; parse it, or switch `DeltaStore.write_records`
  to typed columns for direct SQL/BI querying (recommended before wiring a BI tool).
- **Local (JSON):** `.data/impact_results.json`.

Example (after expanding to typed columns) — a dashboard tile query:

```sql
SELECT system, severity, COUNT(*) AS impacted_assets
FROM insurance.impact_analysis.impact_results
GROUP BY system, severity
ORDER BY severity DESC;
```

The companion tables `nodes` and `edges` let a dashboard render the full dependency
graph or a lineage explorer; `change_requests` records what was analyzed and when.

## Adding a panel to the Streamlit dashboard

The app is a thin view over the engine, so new panels are additive:

1. Add a computation (reuse `analyze_change` / `find_nodes` from `impact.graph`).
2. Render it inside the relevant tab. For a graph visualization, build a subgraph
   from `results[*].path` and render with `pyvis` (already in `requirements.txt`) via
   `streamlit.components.v1.html`.
3. Keep the report **grouped by system + severity** with the `reason` path visible —
   that explainability is the product's credibility.

## Live-mode wiring checklist

1. `config/settings.yaml`: `mode: live`, real `catalogs`/`schemas`,
   `tableau.server/site/token_name/secret_scope`, `mosaic_ai.endpoint`.
2. Databricks secret scope holds the Tableau PAT (`00_setup_catalog.py` shows the CLI).
3. Run notebooks `00 → 10 → 20 → 30 → 40`, or deploy `app/app.yaml`.
4. Same engine, same contract — the dashboard code does not change.
