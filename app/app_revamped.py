"""Change Impact Analysis — Databricks App (Streamlit).

Three surfaces:
  * Propose Change — pick a column + change type, get a graded impact report.
    Click a blast-radius tile to open the dependency graph (expandable to
    full screen), or hand the result to the AI chat with context carried over.
  * Chat — ask "what breaks if I rename policy_status?" in natural language.
  * Documentation — project docs, travelling with the dashboard.

Runs locally (`streamlit run app/app.py`) against sample fixtures and in
Databricks Apps against live metadata, with no code changes.
"""

from __future__ import annotations

import html
import os
import sys

import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from impact.ai.nl_change import parse_nl_change  # noqa: E402
from impact.ai.summarize import summarize_impact  # noqa: E402
from impact.config import load_settings  # noqa: E402
from impact.graph import analyze_change  # noqa: E402
from impact.model import ChangeRequest, ChangeType, NodeType, Severity  # noqa: E402
from impact.pipeline import build_graph_in_memory  # noqa: E402

st.set_page_config(
    page_title="Change Impact Analysis",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Theme — driven by an explicit in-app switch so it applies to *everything*
# (Streamlit's own ⋮ → Settings toggle only repaints Streamlit's chrome; it
# does not re-run the script, so custom CSS never followed it).
# --------------------------------------------------------------------------- #
def _initial_theme() -> str:
    try:
        return st.context.theme.type or "light"
    except Exception:
        return "light"


if "theme" not in st.session_state:
    st.session_state["theme"] = _initial_theme()

_LIGHT = {
    "app": "#ffffff", "ink": "#111214", "ink2": "#5f6368", "ink3": "#9aa0a6",
    "line": "#e8e8e6", "lineSoft": "#f1f1ef",
    "surface": "#ffffff", "surface2": "#fafaf9", "hover": "#00000008",
    "shadow": "rgba(0,0,0,.07)", "scrim": "rgba(255,255,255,.85)",
    "breaking": "#d64545", "warning": "#c07d15", "info": "#3d7de0", "safe": "#4f8f22",
}
_DARK = {
    "app": "#0f1013", "ink": "#e8eaed", "ink2": "#9aa0a6", "ink3": "#70757a",
    "line": "#2d3037", "lineSoft": "#24262b",
    "surface": "#16171b", "surface2": "#1b1d22", "hover": "#ffffff0f",
    "shadow": "rgba(0,0,0,.5)", "scrim": "rgba(10,11,13,.88)",
    "breaking": "#e56a6a", "warning": "#dda63f", "info": "#6ea4ee", "safe": "#7fb95e",
}
DARK = st.session_state["theme"] == "dark"
T = _DARK if DARK else _LIGHT

THEME = f"""
<style>
:root{{
  --app:{T['app']}; --ink:{T['ink']}; --ink-2:{T['ink2']}; --ink-3:{T['ink3']};
  --line:{T['line']}; --line-soft:{T['lineSoft']};
  --surface:{T['surface']}; --surface-2:{T['surface2']}; --hover:{T['hover']};
  --shadow:{T['shadow']}; --scrim:{T['scrim']};
  --breaking:{T['breaking']}; --warning:{T['warning']};
  --info:{T['info']}; --safe:{T['safe']};
  --mono:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace;
}}

/* ---- fonts. NOTE: never use a broad [class*="st-"] font rule; it also hits
   Streamlit's Material icon spans and ligatures render as literal text. ---- */
.stApp, .stApp p, .stApp span, .stApp div, .stApp label, .stApp li{{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
}}
[data-testid="stIconMaterial"], .material-symbols-rounded, .material-icons,
span[class*="material-symbols"], span[class*="material-icons"]{{
  font-family:'Material Symbols Rounded','Material Symbols Outlined',
    'Material Icons'!important;
}}

/* ---- Streamlit surfaces follow our tokens so the switch covers everything ---- */
.stApp{{background:var(--app);}}
[data-testid="stHeader"]{{background:transparent;}}
[data-testid="stSidebar"]{{background:var(--surface-2)!important;
  border-right:1px solid var(--line);}}
[data-testid="stSidebar"] *{{color:var(--ink-2);}}
.stApp, .stApp p, .stApp li{{color:var(--ink-2);}}
h1,h2,h3,h4,h5,h6{{color:var(--ink)!important;}}
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
[data-testid="stTextInput"] input{{
  background:var(--surface)!important;border-color:var(--line)!important;
  color:var(--ink)!important;}}
/* Popovers and the main menu: theme the CONTAINER, not just the items.
   Styling only the <li> left the surrounding list in Streamlit's own theme,
   which showed through as dark bars at the top padding and around every
   divider. Items are transparent so there are no seams. */
[data-testid="stMainMenuPopover"], [data-testid="stMainMenuList"],
[data-baseweb="popover"] ul[role="listbox"], [data-baseweb="menu"]{{
  background:var(--surface)!important;border-color:var(--line)!important;}}
[data-testid="stMainMenuDivider"]{{background:var(--line)!important;
  border-color:var(--line)!important;}}
[data-baseweb="popover"] li, [data-testid="stMainMenuList"] li{{
  background:transparent!important;color:var(--ink)!important;}}
[data-baseweb="popover"] li:hover, [data-testid="stMainMenuList"] li:hover{{
  background:var(--hover)!important;}}
[data-testid="stMainMenuList"] span, [data-testid="stMainMenuList"] div{{
  color:var(--ink-2)!important;}}
.block-container{{padding-top:2.2rem;padding-bottom:4rem;max-width:1220px;}}
footer{{visibility:hidden;}}

/* ---- swap Streamlit's overflow glyph for a settings gear ---- */
[data-testid="stMainMenu"] [data-testid="stIconMaterial"]{{font-size:0!important;}}
[data-testid="stMainMenu"] [data-testid="stIconMaterial"]::after{{
  content:"settings";font-size:1.2rem;line-height:1;
  font-family:'Material Symbols Rounded','Material Icons'!important;
  color:var(--ink-2);}}

/* ---- motion ---- */
@keyframes caIn{{from{{opacity:0;transform:translateY(7px);}}
  to{{opacity:1;transform:none;}}}}
@keyframes caFade{{from{{opacity:0;}}to{{opacity:1;}}}}
.ca-anim{{animation:caIn .3s cubic-bezier(.22,.61,.36,1) both;}}
@media (prefers-reduced-motion:reduce){{
  *,*::before,*::after{{animation:none!important;transition:none!important;}}}}

/* ---- page head ---- */
.ca-title{{font-size:1.65rem;font-weight:680;letter-spacing:-.02em;color:var(--ink);
  margin:0 0 .25rem;}}
.ca-sub{{font-size:.94rem;color:var(--ink-2);margin:0 0 1.8rem;}}
.ca-label{{font-family:var(--mono);font-size:.68rem;font-weight:600;
  letter-spacing:.13em;text-transform:uppercase;color:var(--ink-3);
  display:flex;align-items:center;gap:.7rem;margin:2rem 0 .8rem;}}
.ca-label::after{{content:"";flex:1;height:1px;background:var(--line);}}
.ca-nudge{{font-size:.78rem;color:var(--ink-3);margin:.6rem 0 0;}}

/* ---- blast-radius tiles (real buttons: hover + click affordance) ---- */
.st-key-tiles .stButton button{{
  background:var(--surface);border:1px solid var(--line);border-radius:10px;
  padding:.95rem 1.1rem;text-align:left;height:auto;min-height:5.1rem;
  align-items:flex-start;justify-content:flex-start;cursor:pointer;
  transition:border-color .15s,transform .15s,box-shadow .15s;}}
.st-key-tiles .stButton button:hover{{
  border-color:var(--ink-3);transform:translateY(-2px);
  box-shadow:0 4px 14px var(--shadow);}}
.st-key-tiles .stButton button:active{{transform:translateY(0);}}
.st-key-tiles .stButton button:focus{{box-shadow:0 0 0 2px var(--hover)!important;}}
.st-key-tiles .stButton button p{{
  font-family:var(--mono);font-size:.65rem!important;font-weight:600;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2)!important;
  line-height:1.5;margin:0;}}
.st-key-tiles .stButton button strong{{
  display:block;font-size:1.8rem;font-weight:640;line-height:1.15;
  color:var(--ink);font-variant-numeric:tabular-nums;letter-spacing:-.02em;
  margin-top:.35rem;font-family:-apple-system,sans-serif;}}
.st-key-tiles .stButton button[kind="primary"]{{border-color:var(--ink);}}

.dot{{width:7px;height:7px;border-radius:50%;flex:none;display:inline-block;}}
.dot.breaking{{background:var(--breaking);}}
.dot.warning{{background:var(--warning);}}
.dot.info{{background:var(--info);}}
.dot.total{{background:var(--ink-3);}}
.dot.safe{{background:var(--safe);}}

/* ---- dependency graph ----
   The canvas IS the Streamlit container, so the full-screen control (an
   absolutely-positioned child) is always inside the canvas box, and in full
   screen it is a child of the overlay itself rather than a sibling sitting
   underneath it. */
.st-key-graphwrap{{position:relative;border:1px solid var(--line);
  border-radius:10px;background:var(--surface);padding:1rem 1.1rem;
  overflow:auto;animation:caIn .3s cubic-bezier(.22,.61,.36,1) both;}}
.ca-canvas{{min-width:0;}}
/* full screen is a dedicated VIEW, not an overlay — no fixed positioning and
   no stacking context, so the exit control can never be covered. */
.ca-fspage{{border:1px solid var(--line);border-radius:10px;
  background:var(--surface);padding:1rem 1.1rem;overflow:auto;
  min-height:calc(100vh - 8.5rem);animation:caFade .2s ease both;}}
.ca-fsbar{{display:flex;align-items:center;gap:.75rem;margin-bottom:.7rem;}}
.ca-fshint{{font-family:var(--mono);font-size:.63rem;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink-3);}}
.ca-fshint kbd{{font-family:var(--mono);border:1px solid var(--line);
  border-bottom-width:2px;border-radius:4px;padding:.05rem .3rem;
  background:var(--surface-2);color:var(--ink-2);}}
.ca-legend{{display:flex;gap:1.15rem;flex-wrap:wrap;font-family:var(--mono);
  font-size:.63rem;letter-spacing:.07em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:.85rem;}}
.ca-legend span{{display:inline-flex;align-items:center;gap:.4rem;}}
.gnode rect{{fill:var(--surface-2);stroke:var(--line);stroke-width:1;
  transition:stroke-width .15s;}}
.gnode:hover rect{{stroke-width:2.4;}}
.gnode.breaking rect{{stroke:var(--breaking);stroke-width:1.5;}}
.gnode.warning rect{{stroke:var(--warning);stroke-width:1.5;}}
.gnode.info rect{{stroke:var(--info);stroke-width:1.5;}}
.gnode.root rect{{stroke:var(--ink);stroke-width:2;fill:var(--surface);}}
.gnode .gname{{fill:var(--ink);font-size:11.5px;font-weight:600;}}
.gnode .gkind{{fill:var(--ink-3);font-size:8.5px;letter-spacing:.08em;
  text-transform:uppercase;}}
.gedge{{stroke:var(--ink-3);stroke-width:1.2;fill:none;opacity:.5;}}
.grel{{fill:var(--ink-3);font-size:8.5px;}}

/* full-screen control, pinned inside the canvas top-right. Descendant (not
   child) selectors: Streamlit nests elements in wrapper divs. Margins are
   zeroed so the offset is exactly top/right and never drifts above the box. */
.st-key-graphwrap .st-key-fsbtn{{
  position:absolute;top:.5rem;right:.5rem;z-index:3;width:auto;
  margin:0!important;padding:0!important;}}
.st-key-fsbtn .stButton, .st-key-fsbtn [data-testid="stElementContainer"]{{
  margin:0!important;}}
.st-key-fsbtn .stButton button{{padding:.28rem .4rem;min-height:0;margin:0;
  border-radius:6px;background:var(--surface);border:1px solid var(--line);
  color:var(--ink-2);box-shadow:0 1px 4px var(--shadow);line-height:1;}}
.st-key-fsbtn .stButton button:hover{{border-color:var(--ink-3);
  color:var(--ink);background:var(--surface-2);}}

/* ---- asset rows ---- */
.ca-rows{{border:1px solid var(--line);border-radius:10px;overflow:hidden;}}
.ca-row{{display:grid;grid-template-columns:112px 1fr;gap:1.1rem;
  padding:.9rem 1.15rem;border-bottom:1px solid var(--line-soft);
  background:var(--surface);}}
.ca-row:last-child{{border-bottom:none;}}
.ca-sev{{font-family:var(--mono);font-size:.65rem;font-weight:600;
  letter-spacing:.09em;text-transform:uppercase;display:flex;align-items:center;
  gap:.45rem;padding-top:.16rem;}}
.ca-sev.breaking{{color:var(--breaking);}}
.ca-sev.warning{{color:var(--warning);}}
.ca-sev.info{{color:var(--info);}}
.ca-asset{{font-size:.95rem;font-weight:600;color:var(--ink);margin-bottom:.3rem;
  word-break:break-word;}}
.ca-meta{{display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.45rem;}}
.chip{{font-family:var(--mono);font-size:.63rem;letter-spacing:.05em;
  text-transform:uppercase;color:var(--ink-2);border:1px solid var(--line);
  border-radius:99px;padding:.14rem .5rem;white-space:nowrap;}}
.ca-path{{font-family:var(--mono);font-size:.72rem;color:var(--ink-3);
  line-height:1.6;word-break:break-word;}}
.ca-path b{{color:var(--ink-2);font-weight:600;}}

/* ---- cards ---- */
.ca-card{{border:1px solid var(--line);border-radius:10px;padding:1.2rem 1.4rem;
  background:var(--surface);}}
.ca-card.quiet{{background:var(--surface-2);}}
.ca-card p{{font-size:.92rem;color:var(--ink-2);line-height:1.62;}}
.ca-card p:last-child{{margin-bottom:0;}}
.ca-card strong{{color:var(--ink);font-weight:640;}}
.ca-card code{{font-family:var(--mono);font-size:.85em;background:var(--surface-2);
  border:1px solid var(--line);border-radius:4px;padding:.05rem .3rem;color:var(--ink-2);}}
.ca-card ul{{margin:.5rem 0 .75rem;padding-left:1.1rem;}}
.ca-card li{{font-size:.92rem;color:var(--ink-2);line-height:1.6;margin-bottom:.3rem;}}
.ca-safe{{border:1px solid var(--line);border-radius:10px;padding:1.5rem 1.4rem;
  background:var(--surface);display:flex;gap:.8rem;align-items:flex-start;}}
.ca-safe-t{{font-size:.98rem;font-weight:640;color:var(--ink);margin-bottom:.2rem;}}
.ca-safe-d{{font-size:.9rem;color:var(--ink-2);}}
.ca-read{{border:1px solid var(--line);border-left:2px solid var(--ink);
  border-radius:6px;padding:.75rem 1rem;background:var(--surface-2);
  font-size:.88rem;color:var(--ink-2);margin-bottom:.4rem;}}
.ca-read b{{color:var(--ink);font-weight:640;}}
.ca-read .m{{font-family:var(--mono);font-size:.85em;}}

/* ---- sidebar ---- */
[data-testid="stSidebar"] .block-container{{padding-top:1.8rem;}}
.ca-brand{{display:flex;align-items:center;gap:.6rem;font-weight:680;
  font-size:.93rem;letter-spacing:-.01em;color:var(--ink)!important;margin-bottom:.15rem;}}
.ca-brand-m{{width:22px;height:22px;border-radius:6px;background:var(--ink);
  color:var(--surface)!important;display:flex;align-items:center;
  justify-content:center;font-size:.7rem;flex:none;}}
.ca-brand-s{{font-size:.72rem;color:var(--ink-3)!important;margin:0 0 1.4rem 2.2rem;}}
[data-testid="stSidebar"] [role="radiogroup"]{{gap:.15rem;}}
[data-testid="stSidebar"] [role="radiogroup"] > label{{
  padding:.45rem .6rem;border-radius:7px;transition:background .12s;
  margin:0;width:100%;cursor:pointer;}}
[data-testid="stSidebar"] [role="radiogroup"] > label > div:first-of-type{{
  display:none!important;}}
[data-testid="stSidebar"] [role="radiogroup"] > label:hover{{background:var(--hover);}}
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked){{
  background:var(--hover);}}
[data-testid="stSidebar"] [role="radiogroup"] > label p{{
  font-size:.88rem!important;color:var(--ink-2)!important;}}
[data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) p{{
  color:var(--ink)!important;font-weight:620;}}
.ca-side-l{{font-family:var(--mono);font-size:.63rem;font-weight:600;
  letter-spacing:.13em;text-transform:uppercase;color:var(--ink-3)!important;
  margin:1.3rem 0 .5rem;}}
.ca-side-foot{{border-top:1px solid var(--line);margin-top:1.4rem;padding-top:.9rem;}}
.ca-kv{{display:flex;justify-content:space-between;align-items:center;
  font-size:.76rem;color:var(--ink-3)!important;padding:.2rem 0;}}
.ca-kv b{{color:var(--ink-2)!important;font-weight:600;font-variant-numeric:tabular-nums;}}
.ca-mode{{font-family:var(--mono);font-size:.62rem;letter-spacing:.08em;
  text-transform:uppercase;border:1px solid var(--line);border-radius:99px;
  padding:.1rem .45rem;color:var(--ink-2)!important;background:var(--surface);}}

/* ---- inputs / buttons ---- */
[data-testid="stSelectbox"] label p, [data-testid="stTextInput"] label p{{
  font-family:var(--mono);font-size:.65rem!important;font-weight:600;
  letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3)!important;}}
.stButton button{{border-radius:7px;font-weight:600;font-size:.86rem;
  border:1px solid var(--line);background:var(--surface);color:var(--ink);
  padding:.42rem 1.1rem;transition:background .12s,border-color .12s;}}
.stButton button:hover{{border-color:var(--ink-3);background:var(--surface-2);
  color:var(--ink);}}
/* Streamlit marks primary buttons with data-testid="stBaseButton-primary";
   there is no `kind` DOM attribute, so target the testid (the [kind] selector
   is kept only as a fallback for other Streamlit versions). */
.stButton button[data-testid="stBaseButton-primary"],
.stButton button[kind="primary"]{{
  background:var(--ink)!important;border-color:var(--ink)!important;
  color:var(--app)!important;}}
.stButton button[data-testid="stBaseButton-primary"] p,
.stButton button[kind="primary"] p{{color:var(--app)!important;}}
.stButton button[data-testid="stBaseButton-primary"]:hover,
.stButton button[kind="primary"]:hover{{opacity:.87;}}
</style>
"""
st.markdown(THEME, unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(__file__)
_DOCS = {
    "Overview": os.path.join(_HERE, "..", "README.md"),
    "Architecture": os.path.join(_HERE, "..", "docs", "ARCHITECTURE.md"),
    "Dashboard & Integration": os.path.join(_HERE, "..", "docs", "DASHBOARD.md"),
    "Contributor Onboarding": os.path.join(_HERE, "..", "docs", "AGENT_ONBOARDING.md"),
}
CHANGE_LABELS = {
    ChangeType.ADD: "Add column",
    ChangeType.DROP: "Drop column",
    ChangeType.RENAME: "Rename column",
    ChangeType.RETYPE: "Change datatype",
    ChangeType.LOGIC: "Change logic",
}
_TILE_COLOR = {"breaking": "red", "warning": "orange", "info": "blue", "total": "gray"}


@st.cache_resource
def get_context():
    settings = load_settings()
    return settings, build_graph_in_memory(settings)


def column_options(graph):
    return sorted(
        (d["node"].name, d["node"].id)
        for _, d in graph.nodes(data=True)
        if d["node"].type == NodeType.COLUMN
    )


def _read_doc(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        return f"_Could not load `{path}`: {exc}_"


def label(text):
    st.markdown(f'<div class="ca-label">{html.escape(text)}</div>', unsafe_allow_html=True)


def _kind_label(t):
    return str(t.value).replace("tableau_", "tableau ").replace("_", " ")


# --------------------------------------------------------------------------- #
# Dependency graph
# --------------------------------------------------------------------------- #
def graph_svg(results, sev_filter=None):
    """Layered SVG built from ImpactResult.path.

    Paths alternate [node, relation, node, ...]; even indices are node names
    and index/2 gives the column (depth).
    """
    subset = [r for r in results if not sev_filter or r.severity.value == sev_filter]
    if not subset:
        subset = results
    sev_by_name, kind_by_name = {}, {}
    for r in subset:
        sev_by_name[r.asset_name] = r.severity.value
        kind_by_name[r.asset_name] = _kind_label(r.asset_type)

    depth, order, edges = {}, [], {}
    for r in subset:
        p = r.path
        for i in range(0, len(p), 2):
            name = p[i]
            d = i // 2
            if name not in depth:
                depth[name] = d
                order.append(name)
            else:
                depth[name] = min(depth[name], d)
            if i >= 2:
                rel = p[i - 1].strip("-").replace("->", "").strip()
                edges[(p[i - 2], name)] = rel
    if not order:
        return ""

    NODE_H, GAP_Y, GAP_X, PAD = 46, 16, 78, 12
    by_depth = {}
    for name in order:
        by_depth.setdefault(depth[name], []).append(name)
    depths = sorted(by_depth)

    col_w, col_x, x = {}, {}, PAD
    for d in depths:
        col_w[d] = max(128, min(230, max(len(n) for n in by_depth[d]) * 6.6 + 26))
        col_x[d] = x
        x += col_w[d] + GAP_X
    width = x - GAP_X + PAD
    height = PAD * 2 + max(len(v) for v in by_depth.values()) * (NODE_H + GAP_Y) - GAP_Y

    pos = {}
    for d in depths:
        for i, name in enumerate(by_depth[d]):
            pos[name] = (col_x[d], PAD + i * (NODE_H + GAP_Y), col_w[d])

    parts = []
    for (src, dst), rel in edges.items():
        if src not in pos or dst not in pos:
            continue
        ax, ay, aw = pos[src]
        bx, by, _ = pos[dst]
        x1, y1, x2, y2 = ax + aw, ay + NODE_H / 2, bx, by + NODE_H / 2
        mx = (x1 + x2) / 2
        parts.append(f'<path class="gedge" d="M{x1} {y1} C{mx} {y1} {mx} {y2} {x2} {y2}"/>')
        parts.append(
            f'<text class="grel" x="{mx}" y="{(y1 + y2) / 2 - 5}" '
            f'text-anchor="middle">{html.escape(rel)}</text>'
        )

    root = by_depth[depths[0]][0]
    for name in order:
        nx, ny, nw = pos[name]
        is_root = name == root and depth[name] == 0
        cls = "root" if is_root else sev_by_name.get(name, "")
        kind = "changed column" if is_root else kind_by_name.get(name, "asset")
        shown = name if len(name) <= 30 else name[:29] + "…"
        parts.append(
            f'<g class="gnode {cls}">'
            f'<rect x="{nx}" y="{ny}" width="{nw}" height="{NODE_H}" rx="7">'
            f"<title>{html.escape(name)}</title></rect>"
            f'<text class="gkind" x="{nx + 11}" y="{ny + 17}">{html.escape(kind)}</text>'
            f'<text class="gname" x="{nx + 11}" y="{ny + 34}">{html.escape(shown)}</text>'
            f"</g>"
        )

    legend = (
        '<div class="ca-legend">'
        '<span><span class="dot breaking"></span>Breaking</span>'
        '<span><span class="dot warning"></span>Warning</span>'
        '<span><span class="dot info"></span>Info</span>'
        "<span>Changed node outlined dark &middot; arrows read producer &rarr; consumer</span>"
        "</div>"
    )
    return (
        f"{legend}<svg viewBox='0 0 {width} {height}' width='{width}' "
        f"height='{height}' role='img' aria-label='Dependency paths'>"
        f"{''.join(parts)}</svg>"
    )


# --------------------------------------------------------------------------- #
# Result rendering
# --------------------------------------------------------------------------- #
def _fmt_path(path, reason):
    if path:
        return " ".join(
            html.escape(t) if i % 2 else f"<b>{html.escape(t)}</b>"
            for i, t in enumerate(path)
        )
    return html.escape(reason)


def asset_rows(results):
    rows = []
    for r in sorted(results, key=lambda r: (-r.severity.rank, r.system.value, r.asset_name)):
        sev = r.severity.value
        rows.append(
            f'<div class="ca-row">'
            f'<div class="ca-sev {sev}"><span class="dot {sev}"></span>{sev.upper()}</div>'
            f'<div><div class="ca-asset">{html.escape(r.asset_name)}</div>'
            f'<div class="ca-meta"><span class="chip">{html.escape(r.system.value)}</span>'
            f'<span class="chip">{html.escape(_kind_label(r.asset_type))}</span></div>'
            f'<div class="ca-path">{_fmt_path(r.path, r.reason)}</div></div></div>'
        )
    st.markdown(
        f'<div class="ca-rows ca-anim">{"".join(rows)}</div>', unsafe_allow_html=True
    )


_ESC_JS = """
<script>
// Bind once on the parent document: Escape clicks the exit button if the
// full-screen view is showing. Harmless no-op when it isn't.
(function () {
  var doc = window.parent.document;
  if (doc.__caEscBound) return;
  doc.__caEscBound = true;
  doc.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var host = doc.querySelector('.st-key-fsexitbtn');
    if (!host) return;
    var btn = host.querySelector('button');
    if (btn) { e.preventDefault(); btn.click(); }
  });
})();
</script>
"""


def fullscreen_graph(svg, fs_key, key):
    """A dedicated full-screen view.

    Deliberately NOT an overlay: an earlier version used position:fixed with a
    high z-index, and the exit control kept ending up beneath Streamlit's own
    layers, so clicks never landed. Rendering the graph as the only thing on
    the page keeps the button a plain in-flow widget that cannot be covered.
    """
    st.markdown(
        "<style>"
        '[data-testid="stSidebar"],[data-testid="stToolbar"],'
        '[data-testid="stDecoration"]{display:none!important;}'
        ".block-container{max-width:100%!important;padding:1.1rem 1.4rem 1rem!important;}"
        "</style>",
        unsafe_allow_html=True,
    )
    bar, _ = st.columns([1.15, 5])
    with bar:
        with st.container(key="fsexitbtn"):
            if st.button(
                "Exit full screen",
                icon=":material/fullscreen_exit:",
                key=f"fsexit_{key}",
                use_container_width=True,
                help="Press Esc to exit",
            ):
                st.session_state[fs_key] = False
                st.rerun()
    st.markdown(
        '<div class="ca-fshint">Press <kbd>Esc</kbd> to exit full screen</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="ca-fspage">{svg}</div>', unsafe_allow_html=True)
    components.html(_ESC_JS, height=0)


def render_results(change, results, settings, key="main", offer_ai=False):
    if not results:
        st.markdown(
            '<div class="ca-safe ca-anim"><span class="dot safe" style="margin-top:.42rem"></span>'
            '<div><div class="ca-safe-t">No downstream dependents found</div>'
            '<div class="ca-safe-d">Nothing in the analysed Databricks or Tableau scope '
            "reads this object. Safe to deploy.</div></div></div>",
            unsafe_allow_html=True,
        )
        return

    open_key, fs_key = f"open_{key}", f"fs_{key}"

    # Full screen short-circuits the whole page: graph only, nothing else.
    if st.session_state.get(fs_key):
        sel = st.session_state.get(open_key)
        fullscreen_graph(
            graph_svg(results, sel if sel not in ("unset", "closed") else None),
            fs_key,
            key,
        )
        return

    counts = {s: sum(1 for r in results if r.severity == s) for s in Severity}

    # ---- blast radius: clickable tiles ----
    label("Blast radius")
    tiles = [
        ("breaking", "Breaking", counts[Severity.BREAKING]),
        ("warning", "Warning", counts[Severity.WARNING]),
        ("info", "Info", counts[Severity.INFO]),
        ("total", "Impacted assets", len(results)),
    ]
    with st.container(key="tiles"):
        cols = st.columns(4)
        for i, (slug, text, val) in enumerate(tiles):
            with cols[i]:
                clicked = st.button(
                    f":{_TILE_COLOR[slug]}[●] {text}  \n**{val}**",
                    key=f"tile_{slug}_{key}",
                    use_container_width=True,
                    help="Show the dependency graph for these assets",
                )
                if clicked:
                    sel = None if slug == "total" else slug
                    if st.session_state.get(open_key) == sel:
                        st.session_state[open_key] = "closed"
                    else:
                        st.session_state[open_key] = sel

    opened = st.session_state.get(open_key, "unset")
    if opened == "unset":
        st.markdown(
            '<div class="ca-nudge">Select a tile above to open the dependency graph.</div>',
            unsafe_allow_html=True,
        )
    elif opened != "closed":
        label("Dependency paths")
        svg = graph_svg(results, opened)
        # The container itself is the canvas, so the control is a child of it
        # rather than a sibling positioned against a different box.
        with st.container(key="graphwrap"):
            with st.container(key="fsbtn"):
                if st.button(
                    "",
                    icon=":material/fullscreen:",
                    key=f"fsbtn_{key}",
                    help="View full screen",
                ):
                    st.session_state[fs_key] = True
                    st.rerun()
            st.markdown(f'<div class="ca-canvas">{svg}</div>', unsafe_allow_html=True)

    # ---- impacted assets ----
    label("Impacted assets")
    shown = results
    if opened not in ("unset", "closed") and opened:
        shown = [r for r in results if r.severity.value == opened] or results
    asset_rows(shown)

    # ---- summary + handoff to chat ----
    label("Impact summary")
    st.markdown(
        f'<div class="ca-card ca-anim">{summarize_impact(change, results, settings)}</div>',
        unsafe_allow_html=True,
    )

    if offer_ai:
        st.markdown('<div style="height:.85rem"></div>', unsafe_allow_html=True)
        obj = change.target_node_id.split(":")[-1].split(".")[-1]
        if st.button("Ask AI about this impact  →", type="primary", key=f"toai_{key}"):
            st.session_state["q"] = (
                f"What will be impacted if I {change.change_type.value} {obj}?"
            )
            # A widget's own key cannot be assigned after the widget is
            # instantiated, and the nav radio is built earlier in this run.
            # Stash the request; the sidebar applies it on the next run,
            # before the radio exists.
            st.session_state["_nav_to"] = "Chat"
            st.rerun()


# --------------------------------------------------------------------------- #
# Shell
# --------------------------------------------------------------------------- #
settings, graph = get_context()

with st.sidebar:
    st.markdown(
        '<div class="ca-brand"><span class="ca-brand-m">◈</span>Change Impact</div>'
        '<div class="ca-brand-s">Analysis Platform</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ca-side-l">Analysis</div>', unsafe_allow_html=True)
    # Apply a pending navigation request *before* the radio is instantiated —
    # assigning a widget's key afterwards raises StreamlitAPIException.
    if "_nav_to" in st.session_state:
        st.session_state["nav"] = st.session_state.pop("_nav_to")
    page = st.radio(
        "Navigation",
        ["Propose Change", "Chat", "Documentation"],
        key="nav",
        label_visibility="collapsed",
    )
    st.markdown('<div class="ca-side-l">Appearance</div>', unsafe_allow_html=True)
    want = "dark" if st.toggle("Dark mode", value=DARK, key="dark_toggle") else "light"
    if want != st.session_state["theme"]:
        st.session_state["theme"] = want
        st.rerun()
    st.markdown(
        '<div class="ca-side-foot">'
        f'<div class="ca-kv"><span>Mode</span><span class="ca-mode">{html.escape(settings.mode)}</span></div>'
        f'<div class="ca-kv"><span>Assets</span><b>{graph.number_of_nodes()}</b></div>'
        f'<div class="ca-kv"><span>Dependencies</span><b>{graph.number_of_edges()}</b></div>'
        "</div>",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
if page == "Propose Change":
    st.markdown(
        '<div class="ca-title">Propose a change</div>'
        '<div class="ca-sub">Select a column and a change type to see everything downstream '
        "that depends on it, before you deploy.</div>",
        unsafe_allow_html=True,
    )

    opts = column_options(graph)
    labels = [c[0] for c in opts]
    default = labels.index("policies.policy_status") if "policies.policy_status" in labels else 0

    c1, c2, c3 = st.columns([2.4, 1.6, 1])
    with c1:
        picked = st.selectbox("Column", labels, index=default)
    with c2:
        ctype_label = st.selectbox(
            "Change type",
            [CHANGE_LABELS[c] for c in ChangeType],
            index=list(ChangeType).index(ChangeType.RENAME),
        )
    with c3:
        st.markdown('<div style="height:1.72rem"></div>', unsafe_allow_html=True)
        go = st.button("Analyze impact", type="primary", use_container_width=True)

    ctype = next(c for c in ChangeType if CHANGE_LABELS[c] == ctype_label)

    if go:
        st.session_state["change"] = ChangeRequest(dict(opts)[picked], ctype)
        st.session_state.pop("open_propose", None)
        st.session_state.pop("fs_propose", None)
    elif "change" not in st.session_state:
        st.session_state["change"] = ChangeRequest(dict(opts)[picked], ctype)

    change = st.session_state["change"]
    render_results(
        change, analyze_change(graph, change), settings, key="propose", offer_ai=True
    )

elif page == "Chat":
    st.markdown(
        '<div class="ca-title">Ask about a change</div>'
        '<div class="ca-sub">Describe the change in plain English. The question is resolved '
        "against the dependency graph — the model never invents a dependency.</div>",
        unsafe_allow_html=True,
    )

    q = st.text_input(
        "Question",
        value=st.session_state.get("q", "What will be impacted if I rename policy_status?"),
    )
    if st.button("Ask", type="primary") or "q" not in st.session_state:
        st.session_state["q"] = q

    change = parse_nl_change(st.session_state["q"], graph, settings)
    if change is None:
        st.markdown(
            '<div class="ca-card quiet"><p>Couldn\'t identify the target column or table. '
            "Try naming it explicitly, for example <code>rename policy_status</code>.</p></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ca-read ca-anim">Interpreted as '
            f'<b>{html.escape(change.change_type.value)}</b> on '
            f'<span class="m"><b>{html.escape(change.target_node_id.split(":")[-1])}</b></span>'
            "</div>",
            unsafe_allow_html=True,
        )
        render_results(change, analyze_change(graph, change), settings, key="chat")

else:
    st.markdown(
        '<div class="ca-title">Documentation</div>'
        '<div class="ca-sub">Project documentation, travelling with the dashboard.</div>',
        unsafe_allow_html=True,
    )
    choice = st.radio("Document", list(_DOCS.keys()), horizontal=True)
    st.markdown('<div style="height:.6rem"></div>', unsafe_allow_html=True)
    st.markdown(_read_doc(_DOCS[choice]))
