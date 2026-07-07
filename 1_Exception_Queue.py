import pandas as pd
import streamlit as st

from db import DB_PATH
from exception_logic import build_exception_queue, trade_three_way_detail
from style import inject, page_header, severity_pill, fmt_usd

st.set_page_config(page_title="Trade Lifecycle Console — Exception Queue", layout="wide")
inject()

if not DB_PATH.exists():
    from generate_data import generate
    with st.spinner("Generating synthetic trade data..."):
        generate()

if "price_tolerance_pct" not in st.session_state:
    st.session_state.price_tolerance_pct = 0.005
if "late_conf_sla_days" not in st.session_state:
    st.session_state.late_conf_sla_days = 2

price_tol = st.session_state.price_tolerance_pct
sla_days = st.session_state.late_conf_sla_days

queue = build_exception_queue(price_tol, sla_days)

page_header(
    "Commodity Trade Lifecycle & Exception Management Console",
    "Exception Queue",
    f"Every open exception across all four detection rules. Thresholds in effect: price break "
    f"tolerance {price_tol*100:.1f}%, late confirmation SLA {sla_days} business days.",
)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
type_filter = f1.multiselect("Exception type", sorted(queue["exception_type"].unique()))
severity_filter = f2.multiselect("Severity", ["Critical", "High", "Medium", "Low"])
book_filter = f3.multiselect("Book", sorted(queue["book"].unique()))
cp_filter = f4.multiselect("Counterparty", sorted(queue["counterparty_name"].unique()))

filtered = queue.copy()
if type_filter:
    filtered = filtered[filtered["exception_type"].isin(type_filter)]
if severity_filter:
    filtered = filtered[filtered["severity"].isin(severity_filter)]
if book_filter:
    filtered = filtered[filtered["book"].isin(book_filter)]
if cp_filter:
    filtered = filtered[filtered["counterparty_name"].isin(cp_filter)]

st.caption(f"Showing {len(filtered)} of {len(queue)} open exceptions.")

sort_col = st.selectbox(
    "Sort by",
    ["Severity (default)", "Age (oldest first)", "Notional at risk (highest first)"],
    label_visibility="collapsed",
)
if sort_col == "Age (oldest first)":
    filtered = filtered.sort_values("age_days", ascending=False)
elif sort_col == "Notional at risk (highest first)":
    filtered = filtered.sort_values("notional_at_risk", ascending=False)

display = filtered.copy()
display["Severity"] = display["severity"].apply(severity_pill)
display_table = display[[
    "trade_id", "exception_type", "counterparty_name", "book", "age_days", "Severity", "notional_at_risk", "detail",
]].rename(columns={
    "trade_id": "Trade ID",
    "exception_type": "Type",
    "counterparty_name": "Counterparty",
    "book": "Book",
    "age_days": "Age (days)",
    "notional_at_risk": "Notional at Risk (USD)",
    "detail": "Detail",
})
display_table["Notional at Risk (USD)"] = display_table["Notional at Risk (USD)"].apply(fmt_usd)

st.write(display_table.to_html(escape=False, index=False), unsafe_allow_html=True)

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Drill-down: 3-way comparison for a single trade
# ---------------------------------------------------------------------------
st.markdown("##### Drill into a trade — 3-way comparison")
st.caption(
    "This is the core reconciliation logic: the originally captured deal, the counterparty's "
    "confirmation, and the resulting invoice, compared side by side so every disagreement is visible."
)

trade_ids = sorted(queue["trade_id"].unique().tolist())
if not trade_ids:
    st.info("No open exceptions at the current thresholds.")
else:
    default_idx = 0
    selected_trade = st.selectbox("Trade ID", trade_ids, index=default_idx)
    detail = trade_three_way_detail(selected_trade)

    if detail:
        st.markdown(
            f"**{detail['commodity']}** &nbsp;|&nbsp; {detail['direction']} &nbsp;|&nbsp; "
            f"{detail['counterparty']} &nbsp;|&nbsp; {detail['book']} — {detail['profit_centre']} &nbsp;|&nbsp; "
            f"current stage: **{detail['status']}**"
        )

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            st.markdown("**Captured (Trade Capture)**")
            st.markdown(f"- Price: `{detail['captured']['price']:,.2f}`")
            st.markdown(f"- Quantity: `{detail['captured']['quantity']:,.0f} {detail['captured']['unit']}`")
            st.markdown(f"- Notional: `{fmt_usd(detail['captured']['notional'])}`")

        with col_b:
            st.markdown("**Confirmed (Confirmation)**")
            conf = detail["confirmed"]
            price_flag = "⚠️" if conf["price"] != detail["captured"]["price"] else ""
            qty_flag = "⚠️" if conf["quantity"] != detail["captured"]["quantity"] else ""
            st.markdown(f"- Price: `{conf['price']:,.2f}` {price_flag}")
            st.markdown(f"- Quantity: `{conf['quantity']:,.0f} {detail['captured']['unit']}` {qty_flag}")
            st.markdown(f"- Received: `{conf['received_date']}`")
            st.markdown(f"- Affirmed: `{conf['affirmed']}`")

        with col_c:
            st.markdown("**Invoiced / Settled**")
            inv = detail["invoiced"]
            st.markdown(f"- Invoiced amount: `{fmt_usd(inv['invoiced_amount'])}`")
            st.markdown(f"- Invoice date: `{inv['invoice_date']}`")
            st.markdown(f"- Settlement due: `{inv['settlement_due_date']}`")
            st.markdown(f"- Settled date: `{inv['settled_date'] or '—'}`")
            status_flag = "🔴" if inv["settlement_status"] == "Failed" else ("🟡" if inv["settlement_status"] == "Pending" else "🟢")
            st.markdown(f"- Settlement status: `{inv['settlement_status']}` {status_flag}")

        trade_exceptions = queue[queue["trade_id"] == selected_trade]
        if not trade_exceptions.empty:
            st.markdown("**Exceptions flagged on this trade:**")
            for _, row in trade_exceptions.iterrows():
                st.markdown(f"- {severity_pill(row['severity'])} &nbsp; **{row['exception_type']}** — {row['detail']}", unsafe_allow_html=True)
