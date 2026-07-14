# Action Items — Path to a Serious Working Prototype

Status as of 2026-07-15, verified on this machine:

- ✅ Engine, connectors, extraction, graph, impact analysis, AI layer — built (Milestones 0–4 of the plan)
- ✅ 9/9 tests pass (`pytest -q`)
- ✅ Precision 1.00 / Recall 1.00 on labeled fixtures (`python scripts/validate.py`)
- ✅ Streamlit app boots and serves (verified headless, HTTP 200) in sample mode

The prototype **works offline today**. What remains is (A) environment/repo hygiene,
(B) closing the last plan gaps, (C) proving it against **live** Databricks + Tableau,
and (D) demo readiness. Items are sized S (<½ day), M (½–2 days), L (2–5 days).

---

## Phase A — Environment & repo hygiene *(do first, this machine)*

- [ ] **A1 (S) Remove the broken `.venv`.** It symlinks to a Python 3.14 framework that
      no longer exists on this machine (project was moved). The working env is `venv/`
      (Python 3.9). `rm -rf .venv` and update README's setup instructions.
- [ ] **A2 (M) Rebuild on a supported Python.** Python 3.9 is past end-of-life. Recreate
      the venv on 3.11/3.12 (matches Databricks runtime), re-run `pytest` +
      `scripts/validate.py`, and pin exact versions in `requirements.txt`
      (currently working set: sqlglot 30.12, networkx 3.2.1, streamlit 1.50, pyvis 0.3.2,
      databricks-sdk 0.102, tableauserverclient 0.40).
- [ ] **A3 (S) Put the project under git.** It is not a repo — no history, no rollback.
      `git init`, commit the working baseline, push to GitHub/Azure DevOps (also a
      prerequisite for Databricks Git folders in Phase C).
- [ ] **A4 (S) Fix stale paths in docs.** `docs/AGENT_ONBOARDING.md` and the plan doc
      reference `/Users/priyank/Desktop/RnD/Impact_Analysis`; update to relative paths.

**Exit criteria:** fresh clone + one venv + `pytest` green + app boots, on supported Python.

## Phase B — Close remaining v1 gaps *(sample mode, no credentials needed)*

- [ ] **B1 (M) Dependency-graph visualization in the app.** The plan's Milestone 5 called
      for a pyvis/node-link view of the impact path; pyvis is installed but unused.
      Add a "Graph" panel to the Propose Change tab showing the changed node → impacted
      assets subgraph, colored by severity. High demo value.
- [ ] **B2 (M) Broaden the labeled scenario set.** `fixtures/expected_impact.json` covers
      only 2 scenarios (rename `policy_status`, retype `premium_amount`). Add labeled
      cases for **drop-column, add-column, logic-change, and a table-level change**, plus
      at least one no-impact column, so the precision/recall claim holds across all five
      supported change types. Keep `scripts/validate.py` at 1.00/1.00 or document why not.
- [ ] **B3 (S) Exportable impact report.** Add a "Download report" (CSV or Markdown/HTML)
      button so an engineer can attach the assessment to a change ticket/PR — this is what
      makes it usable in a real release process, not just a demo.
- [ ] **B4 (S) Negative-path polish in Chat.** Verify ambiguous/unknown-column questions
      fail gracefully (suggest closest matching columns rather than a bare warning).

**Exit criteria:** all five change types validated; graph viz renders; report exports.

## Phase C — Live-mode proof *(the step that makes it "serious"; needs access)*

Prereqs to request now (longest lead time): Databricks workspace with Unity Catalog +
`system.access` lineage tables enabled; Tableau site with Metadata API + PAT
(Tableau Catalog/Data Management for upstream-column lineage); a Mosaic AI
pay-per-token Foundation Model endpoint.

- [ ] **C1 (S) Request credentials/permissions above.** File the access requests first —
      everything else in this phase is blocked on them.
- [ ] **C2 (M) Databricks live extraction.** Run `notebooks/00_setup_catalog.py`
      (schema + volume + secret scope), set `mode: live`, run notebook `10` against a real
      target schema. Verify `information_schema` and `system.access.column_lineage`
      queries return data with the granted permissions; fix dialect/permission issues.
- [ ] **C3 (M) Tableau live extraction.** Run notebook `20` against the real site.
      Confirm the Metadata API returns `upstreamColumns` (needs Tableau Catalog); if not
      licensed, implement the planned `.tdsx` XML fallback for column references.
- [ ] **C4 (S) Verify the cross-system bridge on real data.** Spot-check that Tableau
      `databaseColumn`s resolve to real Unity Catalog columns via `maps_to` edges
      (fully-qualified-name matching is the known weak point with custom SQL sources).
- [ ] **C5 (S) Mosaic AI endpoint wiring.** Point `settings.yaml` at the endpoint; confirm
      `summarize` and `nl_change` use it, and that the offline fallback still engages
      when it's unreachable.
- [ ] **C6 (M) Deploy as a Databricks App.** Deploy via `app/app.yaml`, confirm the app
      reads the Delta metadata tables and the demo works end-to-end in the workspace.
- [ ] **C7 (M) Live accuracy check.** Pick 2–3 known real dependencies (a view and a
      dashboard the BI team can vouch for), run the analysis, and have the BI architect
      confirm the impact list — a small "field validation" beats the fixture metric
      for credibility.

**Exit criteria:** the headline question answered correctly against **real** metadata,
inside the Databricks workspace.

## Phase D — Demo & leadership readiness

- [ ] **D1 (S) Rehearse the 3-minute demo** (script already in README): rename
      `policy_status` → 8 breaking assets with paths; contrast with retype → warnings;
      show validate.py metrics.
- [ ] **D2 (S) Capture pitch metrics.** Time a manual impact trace vs the tool
      (<5 min target vs 2–6 hrs), incident anecdotes from the BI team, screenshots or a
      short recording as backup if the live demo fails.
- [ ] **D3 (S) One-page leadership summary.** Investment/benefit numbers from the
      proposal + live-validation results from C7 + the explicit "deferred to phase 2"
      list (notebook/Git/dbt scanning, CI/CD gate, vector search, autonomous agents).

---

## Suggested order & rough timeline

| Week | Focus |
|------|-------|
| 1 | A1–A4, C1 (file access requests immediately), B1 |
| 2 | B2–B4; start C2/C3 as credentials arrive |
| 3 | C2–C5 |
| 4 | C6–C7, D1–D3 |

Phases A and B need no credentials and can start today; Phase C is gated only on access,
which is why C1 is pulled into week 1.
