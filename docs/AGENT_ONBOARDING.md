# Agent Onboarding Prompt — Change Impact Analysis Prototype

> Copy everything below the line and paste it to your coding agent as its first
> message. It brings the agent fully up to speed on what exists and how to
> continue without breaking the design.

---

You are taking over an **in-progress but working** prototype at
`/Users/priyank/Desktop/RnD/Impact_Analysis`. Read this brief fully before editing.
When in doubt, run the tests and the validation script — they encode the intended
behavior.

## 1. What this project is

An **AI-powered Change Impact Analysis platform** for a Databricks + Tableau
analytics stack. Given a proposed Databricks schema change (add / drop / rename /
retype / logic-change on a column or table), it predicts the **downstream blast
radius before deployment** — across Databricks SQL/views **and** Tableau data
sources, calculated fields, worksheets, and dashboards — and returns a graded,
explainable impact report plus a natural-language summary.

Headline demo: *"What breaks if I rename `policy_status`?"* → 8 breaking assets
across 3 Databricks + 5 Tableau objects, each with a dependency path.

## 2. Decisions already locked — do NOT relitigate

- **Databricks-native**: Databricks notebooks + a reusable `src/impact` Python
  package; metadata persisted as Delta tables (Unity Catalog) in production, JSON
  locally. UI is a **Streamlit Databricks App**.
- **Connectors + sample fallback**: real Databricks/Tableau connectors AND
  synthetic fixtures, so everything runs **creds-free in `mode: sample`**.
- **Mosaic AI** for the summary/chat layer — but it is a *thin* layer.
- **v1 coverage**: Databricks SQL/views + Tableau dashboards/data sources.
  **Deferred (out of scope, do not build unless asked)**: notebook scanning,
  Git/dbt scanning, CI/CD deployment gate, vector search, autonomous agents,
  continuous/real-time extraction.

## 3. Current status

Milestones 0–6 complete. **9/9 tests pass. Precision 1.00 / recall 1.00** on the
labeled fixtures. Streamlit app renders through all tabs (verified headlessly).

## 4. How it works (mental model)

```
connectors (sample|live) → extract → unified nodes+edges ("dependency repository")
   → networkx DiGraph (Databricks ↔ Tableau joined at `maps_to` bridges)
   → impact engine (downstream BFS + severity + explanation path)
   → Mosaic AI summary / NL chat  → Streamlit dashboard
```

## 5. Non-negotiable invariants (breaking these breaks the product)

1. **Edge direction is producer → consumer.** `A -> B` means "if A changes, B is
   impacted." Impact analysis is plain reachability from the changed node. Any new
   edge type must follow this direction.
2. **The deterministic graph engine is the source of truth.** The LLM only
   *phrases* summaries and *extracts intent* from chat; it must never introduce an
   impacted asset that isn't in the graph. `nl_change` already validates any
   LLM-extracted target against the graph.
3. **Sample mode must always work with zero credentials.** Every LLM/live call has
   a deterministic offline fallback (`query_llm` returns `None` → fallback path).
4. **Canonical node IDs** (see `model.py` helpers): Databricks identifiers are
   lowercased (`db:column:cat.sch.tbl.col`); Tableau names keep case
   (`tab:field:<datasource>.<field>`). The cross-system bridge works because a
   Databricks column ID is identical whether emitted by extraction or referenced by
   a Tableau `maps_to` edge — don't change the scheme without updating both sides.
5. **Keep tests + `scripts/validate.py` green.** If you add fixtures, update
   `fixtures/expected_impact.json` labels too.

## 6. File map

| Path | Role |
|------|------|
| `src/impact/model.py` | Node/Edge/ChangeRequest/ImpactResult + enums + ID helpers |
| `src/impact/config.py` | loads `config/settings.yaml`; `IMPACT_MODE` override |
| `src/impact/connectors/` | `base` (ABC + factory), `sample` (fixtures), `databricks_live`, `tableau_live` |
| `src/impact/extract/` | `databricks_meta`, `sql_lineage` (sqlglot), `tableau_meta` (+ bridge) |
| `src/impact/graph/` | `build` (networkx), `impact` (BFS + severity + path) |
| `src/impact/ai/` | `llm` (Mosaic AI client), `summarize`, `nl_change` |
| `src/impact/store/delta.py` | `LocalJsonStore` + `DeltaStore` + `get_store` factory |
| `src/impact/pipeline.py` | orchestration: `extract_all`, `build_repository`, `load_graph`, `build_graph_in_memory`, `analyze`, `merge_into_store` |
| `notebooks/00..40` | Databricks notebooks (setup → extract → build graph → demo) |
| `app/app.py` + `app.yaml` | Streamlit dashboard (Propose Change / Chat / Docs) |
| `fixtures/` | sample metadata + `expected_impact.json` ground truth |
| `scripts/validate.py` | precision/recall harness |
| `tests/` | `test_sql_lineage.py`, `test_impact.py` |
| `docs/` | ARCHITECTURE.md, DASHBOARD.md, this file |

## 7. Run & verify

```bash
cd /Users/priyank/Desktop/RnD/Impact_Analysis
source .venv/bin/activate          # venv already exists with deps
pytest -q                          # 9 tests
python scripts/validate.py         # precision/recall == 1.00
streamlit run app/app.py           # dashboard
```

## 8. How to extend (likely next tasks)

- **Go live**: set `mode: live` in `config/settings.yaml`, fill catalog/schema,
  Tableau server/site + secret scope, and the Mosaic AI endpoint; run notebooks
  `00→40`. The live connectors already contain the real `information_schema` /
  `system.access.column_lineage` queries and the Tableau Metadata API GraphQL.
- **New downstream source (e.g. notebooks/dbt)**: add a connector method + an
  `extract/<source>.py` that emits nodes and producer→consumer edges; the engine
  and dashboard pick it up automatically.
- **CI/CD gate**: wrap `pipeline.analyze()` in a job that fails the pipeline when
  any result has `severity == BREAKING`.
- **Typed Delta output**: `DeltaStore` currently stores JSON-string payloads for
  schema-agnostic speed; expand to typed columns if a BI tool reads it directly
  (see DASHBOARD.md § data contract).

## 9. Guardrails

Do not weaken the deterministic core to make the LLM "smarter"; do not add
dependencies without updating `requirements.txt`; do not break sample-mode
reproducibility; keep the impact report grouped by system + severity with a
human-readable `reason` path.
