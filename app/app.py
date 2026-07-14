"""Change Impact Analysis — Databricks App (Streamlit).

Two surfaces:
  * Propose Change — pick a column + change type, get a graded impact report.
  * Chat — ask "what breaks if I rename policy_status?" in natural language.

Runs locally (`streamlit run app/app.py`) against sample fixtures and in
Databricks Apps against live metadata, with no code changes.
"""

from __future__ import annotations

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from impact.ai.nl_change import parse_nl_change  # noqa: E402
from impact.ai.summarize import summarize_impact  # noqa: E402
from impact.config import load_settings  # noqa: E402
from impact.graph import analyze_change  # noqa: E402
from impact.model import ChangeRequest, ChangeType, NodeType, Severity  # noqa: E402
from impact.pipeline import build_graph_in_memory  # noqa: E402

st.set_page_config(page_title="Change Impact Analysis", page_icon="🔎", layout="wide")

_SEV_BADGE = {
    Severity.BREAKING: "🟥 BREAKING",
    Severity.WARNING: "🟧 WARNING",
    Severity.INFO: "🟦 INFO",
}


_HERE = os.path.dirname(__file__)
_DOCS = {
    "Overview (README)": os.path.join(_HERE, "..", "README.md"),
    "Architecture": os.path.join(_HERE, "..", "docs", "ARCHITECTURE.md"),
    "Dashboard & Integration": os.path.join(_HERE, "..", "docs", "DASHBOARD.md"),
    "Agent Onboarding": os.path.join(_HERE, "..", "docs", "AGENT_ONBOARDING.md"),
}


def _read_doc(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        return f"_Could not load `{path}`: {exc}_"


@st.cache_resource
def get_context():
    settings = load_settings()
    graph = build_graph_in_memory(settings)
    return settings, graph


def column_options(graph):
    cols = []
    for _, d in graph.nodes(data=True):
        n = d["node"]
        if n.type == NodeType.COLUMN:
            cols.append((n.name, n.id))
    return sorted(cols)


def render_results(change, results, settings):
    if not results:
        st.success("No downstream dependents found — safe to deploy.")
        st.markdown(summarize_impact(change, results, settings))
        return

    sev_counts = {s: sum(1 for r in results if r.severity == s) for s in Severity}
    c1, c2, c3 = st.columns(3)
    c1.metric("Breaking", sev_counts[Severity.BREAKING])
    c2.metric("Warning", sev_counts[Severity.WARNING])
    c3.metric("Impacted assets", len(results))

    st.subheader("Impacted assets")
    st.dataframe(
        [
            {
                "Severity": _SEV_BADGE[r.severity],
                "System": r.system.value,
                "Type": r.asset_type.value,
                "Asset": r.asset_name,
                "Why": r.reason,
            }
            for r in results
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("AI impact summary")
    st.markdown(summarize_impact(change, results, settings))


settings, graph = get_context()

st.title("🔎 Change Impact Analysis")
st.caption(
    f"Mode: **{settings.mode}** · {graph.number_of_nodes()} assets · "
    f"{graph.number_of_edges()} dependencies · Databricks ↔ Tableau"
)

tab_change, tab_chat, tab_docs = st.tabs(["Propose Change", "Chat", "Docs"])

with tab_change:
    opts = column_options(graph)
    labels = [c[0] for c in opts]
    default = labels.index("policies.policy_status") if "policies.policy_status" in labels else 0
    col1, col2 = st.columns([2, 1])
    with col1:
        picked = st.selectbox("Column", labels, index=default)
    with col2:
        ctype = st.selectbox(
            "Change type", [c.value for c in ChangeType], index=2  # rename
        )
    target_id = dict(opts)[picked]
    if st.button("Analyze impact", type="primary"):
        change = ChangeRequest(target_id, ChangeType(ctype))
        render_results(change, analyze_change(graph, change), settings)

with tab_chat:
    q = st.text_input(
        "Ask about a change",
        value="What will be impacted if I rename policy_status?",
    )
    if st.button("Ask"):
        change = parse_nl_change(q, graph, settings)
        if change is None:
            st.warning("Couldn't identify the target column/table. Try naming it explicitly.")
        else:
            st.info(
                f"Interpreted as **{change.change_type.value}** on "
                f"`{change.target_node_id.split(':')[-1]}`"
            )
            render_results(change, analyze_change(graph, change), settings)

with tab_docs:
    st.caption("Project documentation — travels with the dashboard.")
    choice = st.radio("Document", list(_DOCS.keys()), horizontal=True)
    st.markdown(_read_doc(_DOCS[choice]))
