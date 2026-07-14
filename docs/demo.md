# Live Demo

An interactive, static version of the impact-analysis experience — no server, no
credentials, instant load.

[:material-play-circle: Open the interactive demo](demo-app/index.html){ .md-button .md-button--primary }

## What you're looking at

Every result in the demo is **real engine output**: at site-build time, the
deterministic impact engine (the same `sqlglot` + `networkx` + Tableau-metadata
code that powers the Streamlit app) is run over the synthetic sample fixtures for
**every column × change-type combination**, and the results are precomputed into
the page. Nothing is mocked or hand-written — if the engine changes, the demo
changes on the next deploy.

Try the headline scenario:

1. Column **`policies.policy_status`**, change type **Rename column** →
   **8 breaking assets** across 3 Databricks objects (2 views, 1 query) and
   5 Tableau objects (field, 2 calculated fields, worksheet, dashboard), each with
   the dependency path that explains *why*.
2. Switch to **`policies.premium_amount`** + **Change datatype** → a smaller,
   mostly-warning set — the engine grades severity, it doesn't just flag
   everything as broken.
3. Pick a column with no consumers → "safe to deploy."

## What the full app adds

The static demo covers the *Propose Change* experience. The full Streamlit app
(local or deployed as a Databricks App) additionally offers:

- **Chat** — free-text questions ("what breaks if I rename policy_status?")
  routed through LLM intent extraction into the same deterministic engine.
- **Live mode** — the same engine pointed at your real Unity Catalog metadata and
  Tableau site instead of fixtures.
- **Mosaic AI summaries** — LLM-phrased executive summaries when an endpoint is
  configured (the demo shows the deterministic offline summaries).

See [Run it locally](index.md#run-it-locally-sample-mode-no-credentials) to launch
the full app.
