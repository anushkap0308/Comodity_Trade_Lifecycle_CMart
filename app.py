import altair as alt
import pandas as pd
import streamlit as st

from db import DB_PATH
from exception_logic import build_exception_queue, load_base_tables
from style import inject, page_header, stat_block_html, fmt_usd, brand_mark_svg

st.set_page_config(
    page_title="Trade Lifecycle Console — Overview",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject()

with st.sidebar:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:0.5rem;padding:0.4rem 0 1rem 0;">'
        f'{brand_mark_svg(18)}'
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-weight:600;'
        f'letter-spacing:0.08em;color:#E7E9EC;font-size:0.95rem;">CMART</span></div>',
        unsafe_allow_html=True,
    )

# Bootstrap the synthetic dataset on first run (e.g. a fresh deploy to
# Streamlit Community Cloud / HF Spaces where data/ hasn't been committed).
if not DB_PATH.exists():
    from generate_data import generate
    with st.spinner("Generating synthetic trade data..."):
        generate()

# thresholds live in session_state so the Configuration page can change
# them and every page recomputes against the new values
if "price_tolerance_pct" not in st.session_state:
    st.session_state.price_tolerance_pct = 0.005
if "late_conf_sla_days" not in st.session_state:
    st.session_state.late_conf_sla_days = 2

price_tol = st.session_state.price_tolerance_pct
sla_days = st.session_state.late_conf_sla_days

trades, confirmations, invoices, counterparties = load_base_tables()
queue = build_exception_queue(price_tol, sla_days)

page_header(
    "Commodity Trade Lifecycle & Exception Management Console",
    "Ops Overview",
    "What needs attention today? — open exceptions by type, exposure by desk, and any "
    "counterparty running hot on credit.",
)

# ---------------------------------------------------------------------------
# Top stat row
# ---------------------------------------------------------------------------
open_trades = trades[trades["status"] != "Settled"]
total_notional = (trades["quantity"] * trades["captured_price"]).sum()
n_exceptions = len(queue)
n_trades_with_exceptions = queue["trade_id"].nunique()
over_limit = counterparties[counterparties["credit_used"] / counterparties["credit_limit"] > 0.8]



c1, c2, c3, c4 = st.columns(4)
c1.markdown(
    stat_block_html("Open Trades", f"{len(open_trades)}", f"of {len(trades)} total", icon="briefcase"),
    unsafe_allow_html=True,
)
c2.markdown(stat_block_html("Open Exceptions", f"{n_exceptions}", f"across {n_trades_with_exceptions} trades", icon="magnifier"), unsafe_allow_html=True)
c3.markdown(stat_block_html("Total Notional (captured)", fmt_usd(total_notional), "all trades, USD", icon="coins"), unsafe_allow_html=True)
c4.markdown(stat_block_html("Counterparties Over 80% Credit", f"{len(over_limit)}", "of 9 tracked", icon="shield"), unsafe_allow_html=True)

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Open exceptions by type — bar chart, not a KPI grid
# ---------------------------------------------------------------------------
left, right = st.columns([1.1, 1])

with left:
    st.markdown("##### Open exceptions by type")
    by_type = queue.groupby("exception_type").agg(
        count=("trade_id", "count"),
        notional=("notional_at_risk", "sum"),
    ).reset_index().sort_values("count", ascending=False)

    chart = (
        alt.Chart(by_type)
        .mark_bar(color="#429EDE", size=28)
        .encode(
            x=alt.X("count:Q", title="Open exceptions"),
            y=alt.Y("exception_type:N", sort="-x", title=None),
            tooltip=[
                alt.Tooltip("exception_type:N", title="Type"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("notional:Q", title="Notional at risk", format=",.0f"),
            ],
        )
        .properties(height=180)
        .configure_axis(grid=False, labelColor="#9BA6B5", titleColor="#9BA6B5")
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, use_container_width=True)

with right:
    st.markdown("##### Exposure by book / desk")
    exposure = trades[trades["status"] != "Settled"].copy()
    exposure["notional"] = exposure["quantity"] * exposure["captured_price"]
    by_book = exposure.groupby("book")["notional"].sum().reset_index().sort_values("notional", ascending=False)

    chart2 = (
        alt.Chart(by_book)
        .mark_bar(color="#0F3B62", size=28)
        .encode(
            x=alt.X("notional:Q", title="Open-trade notional (USD)"),
            y=alt.Y("book:N", sort="-x", title=None),
            tooltip=[alt.Tooltip("book:N", title="Book"), alt.Tooltip("notional:Q", title="Notional", format=",.0f")],
        )
        .properties(height=180)
        .configure_axis(grid=False, labelColor="#9BA6B5", titleColor="#9BA6B5")
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart2, use_container_width=True)

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Counterparty credit utilization
# ---------------------------------------------------------------------------
st.markdown("##### Counterparty credit utilization")
st.caption("Counterparties above 80% of their credit limit are highlighted — this is where a new trade "
           "could get stopped at the Validation stage before it ever reaches confirmation.")

cp = counterparties.copy()
cp["utilization_pct"] = cp["credit_used"] / cp["credit_limit"] * 100
cp = cp.sort_values("utilization_pct", ascending=False)


def _row_style(row):
    if row["Utilization %"] > 80:
        return ["background-color: #3A2A28"] * len(row)
    return [""] * len(row)


display_cp = cp[["name", "region", "risk_rating", "credit_limit", "credit_used", "utilization_pct"]].rename(
    columns={
        "name": "Counterparty",
        "region": "Region",
        "risk_rating": "Risk Rating",
        "credit_limit": "Credit Limit (USD)",
        "credit_used": "Credit Used (USD)",
        "utilization_pct": "Utilization %",
    }
)

st.dataframe(
    display_cp.style.apply(_row_style, axis=1).format(
        {"Credit Limit (USD)": "${:,.0f}", "Credit Used (USD)": "${:,.0f}", "Utilization %": "{:.1f}%"}
    ),
    use_container_width=True,
    hide_index=True,
)

if len(over_limit) > 0:
    names = ", ".join(over_limit["name"].tolist())
    st.warning(f"**Credit risk callout:** {names} — currently above 80% of available credit headroom.")

st.markdown(
    '<div class="footnote">Data is synthetic, generated for demonstration purposes. '
    'See the Configuration page to change exception detection thresholds — every page recomputes live.</div>',
    unsafe_allow_html=True,
)