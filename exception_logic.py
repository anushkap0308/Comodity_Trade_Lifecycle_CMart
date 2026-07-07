"""
exception_logic.py

The 3-way matching / exception-detection logic for the console,
kept as standalone functions so they're testable independently of
Streamlit. This is the core operational logic of the whole project:
comparing (a) the captured deal, (b) the counterparty confirmation,
and (c) the invoice, and surfacing every point where they disagree.

All functions take thresholds as explicit arguments (rather than
reading globals) so the Configuration page can change them and
force a clean recompute.
"""

from datetime import date, datetime

import pandas as pd

from db import get_connection

TODAY = date(2026, 7, 7)


def _parse(d):
    if d is None:
        return None
    if isinstance(d, date):
        return d
    return datetime.strptime(str(d), "%Y-%m-%d").date()


def load_base_tables():
    conn = get_connection()
    trades = pd.read_sql_query("SELECT * FROM trades", conn)
    confirmations = pd.read_sql_query("SELECT * FROM confirmations", conn)
    invoices = pd.read_sql_query("SELECT * FROM invoices", conn)
    counterparties = pd.read_sql_query("SELECT * FROM counterparties", conn)
    conn.close()

    for col in ["trade_date", "delivery_start", "delivery_end"]:
        trades[col] = pd.to_datetime(trades[col]).dt.date
    confirmations["received_date"] = pd.to_datetime(confirmations["received_date"]).dt.date
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"]).dt.date
    invoices["settlement_due_date"] = pd.to_datetime(invoices["settlement_due_date"]).dt.date
    invoices["settled_date"] = pd.to_datetime(invoices["settled_date"]).dt.date

    return trades, confirmations, invoices, counterparties


def three_way_view(trades, confirmations, invoices):
    """One row per trade with captured / confirmed / invoiced data joined,
    which is the basis for every exception check and for the drill-down
    comparison shown on the Exception Queue page."""
    df = trades.merge(confirmations, on="trade_id", how="left")
    df = df.merge(invoices, on="trade_id", how="left", suffixes=("", "_inv"))
    df["notional_captured"] = df["quantity"] * df["captured_price"]
    df["notional_confirmed"] = df["confirmed_quantity"] * df["confirmed_price"]
    return df


def severity_from_notional(notional_at_risk: float) -> str:
    """Severity is tied to trade notional value, not treated as uniform.
    A price break on a 50,000-barrel trade matters more than one on a
    500-barrel trade, so thresholds are in absolute USD notional exposed
    by the specific break/mismatch, not just the trade's total size."""
    if notional_at_risk >= 3_000_000:
        return "Critical"
    elif notional_at_risk >= 750_000:
        return "High"
    elif notional_at_risk >= 150_000:
        return "Medium"
    return "Low"


def detect_price_breaks(df: pd.DataFrame, tolerance_pct: float) -> pd.DataFrame:
    d = df.copy()
    d = d[d["confirmed_price"].notna()]
    d["pct_diff"] = (d["confirmed_price"] - d["captured_price"]).abs() / d["captured_price"]
    breaks = d[d["pct_diff"] > tolerance_pct].copy()
    breaks["exception_type"] = "Price Break"
    breaks["notional_at_risk"] = (breaks["confirmed_price"] - breaks["captured_price"]).abs() * breaks["quantity"]
    breaks["detail"] = breaks.apply(
        lambda r: f"Captured {r['captured_price']:.2f} vs confirmed {r['confirmed_price']:.2f} "
                  f"({r['pct_diff']*100:.2f}% diff)",
        axis=1,
    )
    breaks["age_days"] = breaks["received_date"].apply(lambda d0: (TODAY - d0).days if pd.notna(d0) else None)
    return breaks


def detect_quantity_mismatches(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d = d[d["confirmed_quantity"].notna()]
    mism = d[d["confirmed_quantity"] != d["quantity"]].copy()
    mism["exception_type"] = "Quantity Mismatch"
    mism["notional_at_risk"] = (mism["confirmed_quantity"] - mism["quantity"]).abs() * mism["captured_price"]
    mism["detail"] = mism.apply(
        lambda r: f"Captured {r['quantity']:.0f} {r['unit']} vs confirmed {r['confirmed_quantity']:.0f} {r['unit']}",
        axis=1,
    )
    mism["age_days"] = mism["received_date"].apply(lambda d0: (TODAY - d0).days if pd.notna(d0) else None)
    return mism


def detect_late_confirmations(df: pd.DataFrame, sla_days: int) -> pd.DataFrame:
    d = df.copy()
    d = d[d["received_date"].notna()]
    d["days_to_confirm"] = d.apply(lambda r: (r["received_date"] - r["trade_date"]).days, axis=1)
    late = d[d["days_to_confirm"] > sla_days].copy()
    late["exception_type"] = "Late Confirmation"
    late["notional_at_risk"] = late["notional_captured"]
    late["detail"] = late.apply(
        lambda r: f"Confirmed {r['days_to_confirm']} business days after trade date (SLA: {sla_days})",
        axis=1,
    )
    late["age_days"] = late["days_to_confirm"] - sla_days
    return late


def detect_settlement_fails(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    fails = d[
        (d["settlement_due_date"].notna())
        & (d["settlement_due_date"] < TODAY)
        & (d["settlement_status"] != "Settled")
    ].copy()
    fails["exception_type"] = "Settlement Fail"
    fails["notional_at_risk"] = fails["notional_captured"]
    fails["detail"] = fails.apply(
        lambda r: f"Settlement due {r['settlement_due_date']} has passed, status: {r['settlement_status']}",
        axis=1,
    )
    fails["age_days"] = fails["settlement_due_date"].apply(lambda d0: (TODAY - d0).days)
    return fails


def build_exception_queue(price_tolerance_pct: float = 0.005, late_conf_sla_days: int = 2) -> pd.DataFrame:
    trades, confirmations, invoices, counterparties = load_base_tables()
    tw = three_way_view(trades, confirmations, invoices)

    parts = [
        detect_price_breaks(tw, price_tolerance_pct),
        detect_quantity_mismatches(tw),
        detect_late_confirmations(tw, late_conf_sla_days),
        detect_settlement_fails(tw),
    ]

    cols = [
        "trade_id", "exception_type", "counterparty_name" if "counterparty_name" in tw.columns else "counterparty_id",
        "book", "profit_centre", "commodity", "age_days", "notional_at_risk", "detail",
    ]

    cp_lookup = counterparties.set_index("counterparty_id")["name"].to_dict()

    frames = []
    for p in parts:
        if p.empty:
            continue
        p = p.copy()
        p["counterparty_name"] = p["counterparty_id"].map(cp_lookup)
        p["severity"] = p["notional_at_risk"].apply(severity_from_notional)
        keep = [
            "trade_id", "exception_type", "counterparty_name", "book", "profit_centre",
            "commodity", "age_days", "notional_at_risk", "severity", "detail",
        ]
        frames.append(p[keep])

    if not frames:
        return pd.DataFrame(columns=[
            "trade_id", "exception_type", "counterparty_name", "book", "profit_centre",
            "commodity", "age_days", "notional_at_risk", "severity", "detail",
        ])

    queue = pd.concat(frames, ignore_index=True)
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    queue["_sev_sort"] = queue["severity"].map(severity_order)
    queue = queue.sort_values(["_sev_sort", "notional_at_risk"], ascending=[True, False]).drop(columns="_sev_sort")
    return queue.reset_index(drop=True)


def trade_three_way_detail(trade_id: int) -> dict:
    """Full captured / confirmed / invoiced comparison for a single
    trade, used by the Exception Queue drill-down."""
    trades, confirmations, invoices, counterparties = load_base_tables()
    tw = three_way_view(trades, confirmations, invoices)
    row = tw[tw["trade_id"] == trade_id]
    if row.empty:
        return None
    r = row.iloc[0]
    cp_name = counterparties.set_index("counterparty_id")["name"].get(r["counterparty_id"], "Unknown")

    return {
        "trade_id": trade_id,
        "counterparty": cp_name,
        "commodity": r["commodity"],
        "direction": r["direction"],
        "book": r["book"],
        "profit_centre": r["profit_centre"],
        "captured": {
            "price": r["captured_price"],
            "quantity": r["quantity"],
            "unit": r["unit"],
            "notional": r["notional_captured"],
        },
        "confirmed": {
            "price": r.get("confirmed_price"),
            "quantity": r.get("confirmed_quantity"),
            "received_date": r.get("received_date"),
            "affirmed": bool(r.get("affirmed")) if pd.notna(r.get("affirmed")) else None,
            "notional": r.get("notional_confirmed"),
        },
        "invoiced": {
            "invoiced_amount": r.get("invoiced_amount"),
            "invoice_date": r.get("invoice_date"),
            "settlement_due_date": r.get("settlement_due_date"),
            "settled_date": r.get("settled_date"),
            "settlement_status": r.get("settlement_status"),
        },
        "status": r["status"],
    }


def lifecycle_timeline(trade_id: int) -> list:
    """Returns the 7-stage timeline with a date/status for each stage,
    for the Trade Lifecycle View page."""
    trades, confirmations, invoices, counterparties = load_base_tables()
    trow = trades[trades["trade_id"] == trade_id]
    if trow.empty:
        return None
    t = trow.iloc[0]
    conf = confirmations[confirmations["trade_id"] == trade_id]
    inv = invoices[invoices["trade_id"] == trade_id]

    from db import LIFECYCLE_STAGES
    reached_idx = LIFECYCLE_STAGES.index(t["status"])

    stages = []
    stage_dates = {
        "Captured": t["trade_date"],
        "Enriched": t["trade_date"],
        "Validated": t["trade_date"],
        "Confirmed": conf.iloc[0]["received_date"] if not conf.empty else None,
        "Allocated": t["delivery_start"],
        "Invoiced": inv.iloc[0]["invoice_date"] if not inv.empty else None,
        "Settled": inv.iloc[0]["settled_date"] if not inv.empty else None,
    }
    for i, stage in enumerate(LIFECYCLE_STAGES):
        stages.append({
            "stage": stage,
            "reached": i <= reached_idx,
            "date": stage_dates.get(stage),
            "is_current": i == reached_idx,
        })
    return stages
