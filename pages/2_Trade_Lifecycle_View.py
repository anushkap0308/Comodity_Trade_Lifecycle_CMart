import streamlit as st

from db import LIFECYCLE_STAGES, DB_PATH
from exception_logic import load_base_tables, lifecycle_timeline
from style import inject, page_header

st.set_page_config(page_title="Trade Lifecycle Console — Lifecycle View", layout="wide")
inject()

if not DB_PATH.exists():
    from generate_data import generate
    with st.spinner("Generating synthetic trade data..."):
        generate()

trades, confirmations, invoices, counterparties = load_base_tables()

page_header(
    "Commodity Trade Lifecycle & Exception Management Console",
    "Trade Lifecycle View",
    "Pick a single trade and follow it through the seven stages a physical commodity deal moves "
    "through — from capture to settlement.",
)

cp_lookup = counterparties.set_index("counterparty_id")["name"].to_dict()
trades_display = trades.copy()
trades_display["counterparty_name"] = trades_display["counterparty_id"].map(cp_lookup)
trades_display["label"] = trades_display.apply(
    lambda r: f"#{r['trade_id']} — {r['commodity']} / {r['counterparty_name']} / {r['trade_date']}", axis=1
)

selected_label = st.selectbox("Select a trade", trades_display["label"].tolist())
selected_id = int(selected_label.split("—")[0].strip().lstrip("#"))

timeline = lifecycle_timeline(selected_id)
trow = trades[trades["trade_id"] == selected_id].iloc[0]

st.markdown(
    f"**{trow['commodity']}** &nbsp;|&nbsp; {trow['direction']} &nbsp;|&nbsp; "
    f"{trow['quantity']:,.0f} {trow['unit']} @ {trow['captured_price']:,.2f} {trow['currency']} "
    f"&nbsp;|&nbsp; {trow['book']} — {trow['profit_centre']}"
)

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Horizontal stepper
# ---------------------------------------------------------------------------
cols = st.columns(len(LIFECYCLE_STAGES))
for i, (col, stage_info) in enumerate(zip(cols, timeline)):
    with col:
        if stage_info["is_current"]:
            dot_color = "#C9A24B"
            label_color = "#E7E9EC"
        elif stage_info["reached"]:
            dot_color = "#4F8A6B"
            label_color = "#9BA6B5"
        else:
            dot_color = "#2C3446"
            label_color = "#5C6779"

        date_str = str(stage_info["date"]) if stage_info["date"] else "—"

        st.markdown(
            f"""
            <div style="text-align:center;">
                <div style="width:16px;height:16px;border-radius:50%;background:{dot_color};
                            margin:0 auto 6px auto;"></div>
                <div style="font-family:'IBM Plex Mono',monospace;font-size:0.7rem;
                            color:{label_color};text-transform:uppercase;letter-spacing:0.05em;">
                    {stage_info['stage']}
                </div>
                <div style="font-size:0.72rem;color:#5C6779;margin-top:2px;">{date_str}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if i < len(LIFECYCLE_STAGES) - 1:
            bar_color = "#4F8A6B" if timeline[i + 1]["reached"] else "#2C3446"
            st.markdown(
                f'<div style="height:2px;background:{bar_color};margin-top:8px;"></div>',
                unsafe_allow_html=True,
            )

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)

current_stage = next(s["stage"] for s in timeline if s["is_current"])
st.markdown(f"**Current stage: `{current_stage}`** — trade status as recorded in the `trades` table.")

if trow["status"] == "Invoiced":
    st.caption("This trade has been invoiced but has not moved to Settled — check the Exception Queue "
               "for a possible settlement fail.")
elif trow["status"] == "Settled":
    st.caption("This trade has completed its full lifecycle.")
else:
    st.caption("This trade is still short of Confirmation/Allocation — typically because a break is "
               "unresolved further back in the queue.")
