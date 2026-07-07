import streamlit as st

from db import DB_PATH
from exception_logic import build_exception_queue
from style import inject, page_header

st.set_page_config(page_title="Trade Lifecycle Console — Configuration", layout="wide")
inject()

if not DB_PATH.exists():
    from generate_data import generate
    with st.spinner("Generating synthetic trade data..."):
        generate()

if "price_tolerance_pct" not in st.session_state:
    st.session_state.price_tolerance_pct = 0.005
if "late_conf_sla_days" not in st.session_state:
    st.session_state.late_conf_sla_days = 2

page_header(
    "Commodity Trade Lifecycle & Exception Management Console",
    "Configuration",
    "These aren't hardcoded thresholds — they're the same business rules a real ops team would tune "
    "per counterparty or per commodity. Changing them recomputes the exception queue immediately.",
)

col1, col2 = st.columns(2)

with col1:
    st.markdown("##### Price break tolerance")
    st.caption("A confirmation is flagged as a price break when it differs from the captured price by "
               "more than this percentage.")
    new_tol = st.slider(
        "Tolerance (%)",
        min_value=0.1, max_value=3.0,
        value=st.session_state.price_tolerance_pct * 100,
        step=0.1,
        format="%.1f%%",
    )
    st.session_state.price_tolerance_pct = new_tol / 100

with col2:
    st.markdown("##### Late confirmation SLA")
    st.caption("A confirmation is flagged as late when it arrives more than this many business days "
               "after the trade date.")
    new_sla = st.slider(
        "SLA (business days)",
        min_value=1, max_value=10,
        value=st.session_state.late_conf_sla_days,
        step=1,
    )
    st.session_state.late_conf_sla_days = new_sla

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

queue = build_exception_queue(st.session_state.price_tolerance_pct, st.session_state.late_conf_sla_days)

st.markdown("##### Recomputed exception queue at current thresholds")
summary = queue.groupby("exception_type").size().reset_index(name="Open count").rename(
    columns={"exception_type": "Exception type"}
)
st.dataframe(summary, use_container_width=True, hide_index=True)
st.caption(
    f"Total open exceptions at these thresholds: **{len(queue)}** across "
    f"**{queue['trade_id'].nunique()}** trades. Go to the Exception Queue page to see the full list — "
    "it reads these same session-level threshold values."
)

st.markdown(
    '<div class="footnote">Note: quantity mismatch and settlement fail detection do not have '
    'configurable thresholds in this demo — a quantity mismatch is any non-zero difference, and a '
    'settlement fail is any trade past its settlement due date that has not settled. A production '
    'system would likely allow a small quantity tolerance and a grace-period window here too.</div>',
    unsafe_allow_html=True,
)
