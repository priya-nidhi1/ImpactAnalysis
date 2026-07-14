# Architecture

## Overview

The system normalizes metadata from two systems (Databricks, Tableau) into one
**dependency graph**, then answers impact questions as a **downstream reachability
walk** over that graph. An LLM layer phrases the results but is never authoritative.

```
┌─ connectors ─────────────┐
│ sample (fixtures)        │   mode: sample | live
│ databricks_live          │
│ tableau_live             │
└──────────┬───────────────┘
           │ raw metadata dicts
┌──────────▼───────────────┐
│ extract                  │  databricks_meta · sql_lineage (sqlglot) · tableau_meta
└──────────┬───────────────┘
           │ Node[] + Edge[]  ("dependency repository")
┌──────────▼───────────────┐   persisted by store: Delta (live) | JSON (local)
│ graph.build (networkx)   │  Databricks ↔ Tableau joined at `maps_to`
└──────────┬───────────────┘
┌──────────▼───────────────┐
│ graph.impact             │  downstream BFS → severity → explanation path
└──────────┬───────────────┘
┌──────────▼───────────────┐
│ ai.summarize / nl_change │  Mosaic AI (thin) + deterministic fallback
└──────────┬───────────────┘
┌──────────▼───────────────┐
│ Streamlit dashboard      │  Propose Change · Chat · Docs
└──────────────────────────┘
```

## Data model (`src/impact/model.py`)

Everything is a `Node` or an `Edge`.

### Node types
`catalog`, `schema`, `table`, `view`, `column`, `query` (Databricks);
`tableau_datasource`, `tableau_field`, `tableau_calc_field`, `tableau_worksheet`,
`tableau_dashboard` (Tableau).

### Edge types and the direction invariant
**Edges point producer → consumer** — `A -> B` means "if A changes, B is impacted."

| Edge | From → To | Meaning |
|------|-----------|---------|
| `contains` | table → column | structural (drives table-level change fan-out) |
| `derives_from` | column → column | column lineage (materialized derived columns) |
| `references` | column → view/query | SQL reads the column |
| `maps_to` | **databricks column → tableau field** | **cross-system bridge** |
| `computed_from` | field → calc field | calc formula uses the field |
| `used_in` | field → worksheet, worksheet → dashboard | placement |

Because the direction is uniform, **impact = every node reachable from the changed
node** via a BFS. No special-casing per edge type.

### Canonical node IDs
- Databricks (case-insensitive → lowercased): `db:table:cat.sch.tbl`,
  `db:view:cat.sch.view`, `db:column:cat.sch.tbl.col`, `db:query:<id>`.
- Tableau (case-preserving): `tab:datasource:<name>`, `tab:field:<ds>.<field>`,
  `tab:calc:<ds>.<field>`, `tab:worksheet:<name>`, `tab:dashboard:<name>`.

The bridge works because a Tableau field's `upstreamColumns` resolves to the **same**
`db:column:...` ID that Databricks extraction emits.

## Extraction

- **`databricks_meta.extract_databricks`** — `information_schema.tables/columns/views`
  → table/view/column nodes + `contains` edges.
- **`sql_lineage`** — `referenced_columns()` parses view + query SQL with **sqlglot**:
  it qualifies columns against the known table schema (resolving aliases, expanding
  `*`) and returns fully-qualified `cat.sch.tbl.col`. `extract_sql` turns these into
  `references` edges (column → view/query). This is what makes SQL impact *real*
  rather than only query-history-derived.
- **`tableau_meta.extract_tableau`** — datasources/fields/calc-fields/worksheets/
  dashboards → nodes; `maps_to` (bridge), `computed_from` (parsed from `[Field]`
  formula references), and `used_in` edges.

Dangling edges (endpoints outside the analyzed scope) are dropped safely at graph
build time (`graph/build.py` only keeps edges whose both endpoints are real nodes).

## Impact engine (`src/impact/graph/impact.py`)

`analyze_change(graph, change)`:
1. If the target node isn't in the graph (e.g. `add` of a brand-new column), return
   `[]` — no existing dependents.
2. BFS downstream, tracking predecessors for path reconstruction.
3. Keep only **reportable** node types (views, queries, and all Tableau assets);
   hide structural intermediates (raw columns).
4. Assign **severity** and build a human-readable `reason` path.
5. Sort most-severe first, then by system.

### Severity rules
| Change type | Base severity | Escalation |
|-------------|---------------|-----------|
| `rename`, `drop` | BREAKING | — |
| `retype` | WARNING | → BREAKING if it reaches a Tableau calculated field |
| `logic` | WARNING | — |
| `add` | INFO | (usually no dependents) |

## AI layer (`src/impact/ai/`)

- **`llm.query_llm`** — calls a Databricks Foundation Model serving endpoint via the
  SDK's OpenAI-compatible client. Returns `None` if no endpoint is configured or
  reachable → callers fall back to deterministic output.
- **`summarize.summarize_impact`** — feeds the *structured* results to the model with
  a system prompt that forbids inventing assets; deterministic templated summary
  otherwise (same facts, different phrasing).
- **`nl_change.parse_nl_change`** — extracts `{target, change_type}` from a question.
  LLM extraction is validated against the graph; a keyword resolver is the fallback.

## Storage & data contract (`src/impact/store/delta.py`)

Four collections: `nodes`, `edges`, `change_requests`, `impact_results`.

- **`LocalJsonStore`** — one JSON array file per collection under `.data/` (local/tests).
- **`DeltaStore`** — one Delta table per collection in
  `{catalog}.{metadata_schema}.<collection>`, each row a JSON-string `payload`
  column (schema-agnostic for the prototype). `get_store()` auto-selects Delta when a
  Spark session is active, else JSON.

Record shapes (JSON):

```jsonc
// nodes
{ "id", "type", "name", "system", "properties": { ... } }
// edges
{ "src", "dst", "type", "properties": { ... } }
// change_requests
{ "target_node_id", "change_type", "details": { ... } }
// impact_results
{ "asset_id", "asset_name", "asset_type", "system", "severity", "reason", "path": [ ... ] }
```

`impact_results` is the table any external BI dashboard should read — see
[DASHBOARD.md](DASHBOARD.md).

## Configuration (`config/settings.yaml`)

`mode` (`sample`|`live`, override with `IMPACT_MODE`), target `catalogs`/`schemas`,
`sql_dialect`, Tableau `server`/`site`/`token_name`/`secret_scope`, Mosaic AI
`endpoint`, and storage `metadata_schema`/`data_dir`.

## Testing & validation

- `tests/test_sql_lineage.py` — sqlglot column resolution (aliases, `*`, functions).
- `tests/test_impact.py` — exact impacted-set match, severity, NL routing, summary.
- `scripts/validate.py` — precision/recall vs `fixtures/expected_impact.json`.
