"""
generate_data.py

Synthetic data generator for the Commodity Trade Lifecycle console.

This is the part of the project that most determines whether the
final product looks like a real ops queue or randomly-perturbed
noise, so the injection patterns below are hand-designed rather than
applying a single uniform random perturbation to every trade:

  - A SMALL number of large, severe price breaks (the ones that would
    actually get escalated to a desk head).
  - A LARGER number of small, aging price breaks / quantity mismatches
    that sit around in the queue the way real backlogs do.
  - A CLUSTER of late confirmations concentrated on one specific
    counterparty who is known to be slow (this is what makes the
    "ownership" angle of the exception queue mean something).
  - A small number of settlement fails, mostly tied to trades that
    already had an unresolved upstream break.
  - Exactly one counterparty deliberately parked near its credit
    limit, to feed the credit-risk callout on the Overview page.

Run this once to (re)build data/trade_lifecycle.db:
    python generate_data.py
"""

import random
from datetime import date, timedelta

from db import reset_db, LIFECYCLE_STAGES

random.seed(42)

TODAY = date(2026, 7, 7)  # anchor date so the "aging" story stays stable

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

COUNTERPARTIES = [
    # name, region, risk_rating, credit_limit
    ("Meridian Commodities Trading", "Houston, US", "A", 45_000_000),
    ("Northgate Energy Partners", "Houston, US", "BBB", 30_000_000),
    ("Ashford Metals & Mining", "London, UK", "A", 25_000_000),
    ("Solara Resources Group", "Geneva, CH", "BBB", 20_000_000),   # -> parked near limit
    ("Ironbridge Energy Trading", "Singapore, SG", "A", 35_000_000),
    ("Continental Grain & Softs", "Chicago, US", "BBB", 18_000_000),
    ("Halcyon Trading House", "London, UK", "BB", 15_000_000),      # -> slow confirmer
    ("Cascade Commodities Partners", "Calgary, CA", "A", 22_000_000),
    ("Sterling Energy Marketing", "Houston, US", "BBB", 28_000_000),
]

# commodity -> (unit, price_range, qty_range, book, profit_centre)
COMMODITIES = {
    "Crude Oil":    dict(unit="bbl",  price=(68, 92),      qty=(10_000, 100_000), book="Crude Desk",  pc="Houston Physical Crude"),
    "Natural Gas":  dict(unit="MMBtu", price=(2.1, 4.8),   qty=(50_000, 500_000), book="Gas Desk",    pc="Houston Gas & Power"),
    "Copper":       dict(unit="mt",   price=(7_800, 9_600), qty=(500, 5_000),     book="Metals Desk", pc="London Base Metals"),
    "Aluminum":     dict(unit="mt",   price=(2_150, 2_650), qty=(1_000, 8_000),   book="Metals Desk", pc="London Base Metals"),
    "Wheat":        dict(unit="mt",   price=(195, 285),    qty=(1_000, 10_000),   book="Agri Desk",   pc="Chicago Grain & Softs"),
    "Coffee":       dict(unit="lb",   price=(1.45, 2.55),  qty=(100_000, 500_000), book="Agri Desk",  pc="Chicago Grain & Softs"),
}

N_TRADES = 210
SLOW_COUNTERPARTY = "Halcyon Trading House"     # cluster of late confirmations
NEAR_LIMIT_COUNTERPARTY = "Solara Resources Group"


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def build_counterparties(conn):
    rows = []
    for i, (name, region, rating, limit) in enumerate(COUNTERPARTIES, start=1):
        if name == NEAR_LIMIT_COUNTERPARTY:
            used = limit * random.uniform(0.86, 0.93)   # deliberately near limit
        else:
            used = limit * random.uniform(0.15, 0.65)
        rows.append((i, name, limit, round(used, 2), region, rating))
    conn.executemany(
        "INSERT INTO counterparties VALUES (?,?,?,?,?,?)", rows
    )
    conn.commit()
    return {name: i for i, (name, *_r) in enumerate(COUNTERPARTIES, start=1)}


def make_trade(trade_id, cp_id, cp_name, commodity):
    spec = COMMODITIES[commodity]
    trade_date = random_date(TODAY - timedelta(days=120), TODAY - timedelta(days=5))
    quantity = round(random.uniform(*spec["qty"]), 0)
    price = round(random.uniform(*spec["price"]), 2)
    direction = random.choice(["Buy", "Sell"])
    delivery_start = trade_date + timedelta(days=random.randint(5, 20))
    delivery_end = delivery_start + timedelta(days=random.randint(1, 10))

    return dict(
        trade_id=trade_id,
        trade_date=trade_date,
        counterparty_id=cp_id,
        counterparty_name=cp_name,
        commodity=commodity,
        direction=direction,
        quantity=quantity,
        unit=spec["unit"],
        captured_price=price,
        currency="USD",
        delivery_start=delivery_start,
        delivery_end=delivery_end,
        book=spec["book"],
        profit_centre=spec["pc"],
    )


def generate():
    conn = reset_db()
    cp_ids = build_counterparties(conn)
    cp_names = list(cp_ids.keys())
    commodities = list(COMMODITIES.keys())

    trades = []
    for tid in range(1, N_TRADES + 1):
        cp_name = random.choice(cp_names)
        commodity = random.choice(commodities)
        trades.append(make_trade(tid, cp_ids[cp_name], cp_name, commodity))

    # -----------------------------------------------------------------
    # Decide which trades get which exception pattern (hand-designed,
    # not uniform-random). ~15-20% of N_TRADES total across all
    # categories, with deliberate overlap in a couple of cases (a trade
    # that has both a price break AND ends up failing settlement,
    # because in real ops backlogs unresolved breaks are exactly the
    # trades that also blow through settlement dates).
    # -----------------------------------------------------------------
    all_ids = [t["trade_id"] for t in trades]
    random.shuffle(all_ids)

    n_severe_breaks = 7
    n_small_breaks = 14
    n_qty_mismatches = 9
    n_late_conf_cluster = 10   # concentrated on SLOW_COUNTERPARTY
    n_settlement_fail_extra = 6

    severe_break_ids = set(all_ids[:n_severe_breaks])
    small_break_ids = set(all_ids[n_severe_breaks:n_severe_breaks + n_small_breaks])
    qty_mismatch_ids = set(
        all_ids[n_severe_breaks + n_small_breaks: n_severe_breaks + n_small_breaks + n_qty_mismatches]
    )

    # Re-tag some trades onto the slow counterparty so the late-confirmation
    # cluster reads as a real pattern rather than scattered noise.
    slow_cp_id = cp_ids[SLOW_COUNTERPARTY]
    slow_pool = [t for t in trades if t["trade_id"] not in severe_break_ids][:n_late_conf_cluster + 3]
    late_conf_ids = set()
    for t in slow_pool[:n_late_conf_cluster]:
        t["counterparty_id"] = slow_cp_id
        t["counterparty_name"] = SLOW_COUNTERPARTY
        late_conf_ids.add(t["trade_id"])

    remaining_for_settlement = [
        tid for tid in all_ids
        if tid not in severe_break_ids and tid not in late_conf_ids
    ]
    settlement_fail_ids = set(remaining_for_settlement[:n_settlement_fail_extra]) | (
        severe_break_ids & set(all_ids[:3])  # a couple of severe breaks also fail settlement
    )

    trade_rows = []
    confirmation_rows = []
    invoice_rows = []
    conf_id = 1
    inv_id = 1

    for t in trades:
        tid = t["trade_id"]
        trade_date = t["trade_date"]

        # --- confirmation timing -------------------------------------------------
        if tid in late_conf_ids:
            received_date = trade_date + timedelta(days=random.randint(5, 12))  # breaches 2-day SLA
        else:
            received_date = trade_date + timedelta(days=random.randint(0, 2))

        # --- confirmed price / quantity vs. captured ------------------------------
        confirmed_price = t["captured_price"]
        confirmed_quantity = t["quantity"]

        if tid in severe_break_ids:
            pct = random.uniform(0.02, 0.06) * random.choice([-1, 1])  # 2-6% severe break
            confirmed_price = round(t["captured_price"] * (1 + pct), 2)
        elif tid in small_break_ids:
            pct = random.uniform(0.006, 0.018) * random.choice([-1, 1])  # small but > 0.5% tolerance
            confirmed_price = round(t["captured_price"] * (1 + pct), 2)

        if tid in qty_mismatch_ids:
            qty_pct = random.uniform(0.01, 0.08) * random.choice([-1, 1])
            confirmed_quantity = round(t["quantity"] * (1 + qty_pct), 0)

        affirmed = 0 if (tid in severe_break_ids or tid in qty_mismatch_ids) else 1

        # --- lifecycle status ------------------------------------------------------
        if tid in settlement_fail_ids:
            status = "Invoiced"  # invoiced but never settled -> settlement fail
        elif tid in severe_break_ids or tid in qty_mismatch_ids:
            status = random.choice(["Confirmed", "Allocated", "Invoiced"])
        else:
            status = "Settled"

        notional = confirmed_quantity * confirmed_price

        trade_rows.append((
            tid, str(trade_date), t["counterparty_id"], t["commodity"], t["direction"],
            t["quantity"], t["unit"], t["captured_price"], t["currency"],
            str(t["delivery_start"]), str(t["delivery_end"]), t["book"], t["profit_centre"], status,
        ))

        confirmation_rows.append((
            conf_id, tid, confirmed_price, confirmed_quantity, str(received_date), affirmed
        ))
        conf_id += 1

        # --- invoice / settlement ----------------------------------------------------
        invoice_date = received_date + timedelta(days=random.randint(1, 3))
        settlement_due = t["delivery_end"] + timedelta(days=random.randint(3, 10))

        if tid in settlement_fail_ids:
            settled_date = None
            settlement_status = "Failed" if settlement_due < TODAY else "Pending"
        elif status == "Settled":
            settled_date = settlement_due - timedelta(days=random.randint(0, 2))
            settlement_status = "Settled"
        else:
            settled_date = None
            settlement_status = "Pending"

        invoice_rows.append((
            inv_id, tid, round(notional, 2), str(invoice_date), str(settlement_due),
            str(settled_date) if settled_date else None, settlement_status,
        ))
        inv_id += 1

    conn.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", trade_rows
    )
    conn.executemany(
        "INSERT INTO confirmations VALUES (?,?,?,?,?,?)", confirmation_rows
    )
    conn.executemany(
        "INSERT INTO invoices VALUES (?,?,?,?,?,?,?)", invoice_rows
    )
    conn.commit()
    conn.close()

    print(f"Generated {len(trade_rows)} trades across {len(COUNTERPARTIES)} counterparties.")
    print(f"  Severe price breaks: {len(severe_break_ids)}")
    print(f"  Small/aging price breaks: {len(small_break_ids)}")
    print(f"  Quantity mismatches: {len(qty_mismatch_ids)}")
    print(f"  Late confirmations (clustered on {SLOW_COUNTERPARTY}): {len(late_conf_ids)}")
    print(f"  Settlement fails: {len(settlement_fail_ids)}")
    print(f"  Counterparty near credit limit: {NEAR_LIMIT_COUNTERPARTY}")


if __name__ == "__main__":
    generate()
