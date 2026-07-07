"""
db.py — schema definition + connection helper for the
Commodity Trade Lifecycle & Exception Management Console.

SQLite is used deliberately: no server, portable, single file,
matches the "deployable demo" pattern used elsewhere in this
project set.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "trade_lifecycle.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS counterparties (
    counterparty_id INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    credit_limit     REAL NOT NULL,
    credit_used      REAL NOT NULL,
    region           TEXT NOT NULL,
    risk_rating      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY,
    trade_date      TEXT NOT NULL,
    counterparty_id INTEGER NOT NULL REFERENCES counterparties(counterparty_id),
    commodity       TEXT NOT NULL,
    direction       TEXT NOT NULL,      -- Buy / Sell
    quantity        REAL NOT NULL,
    unit            TEXT NOT NULL,
    captured_price  REAL NOT NULL,
    currency        TEXT NOT NULL,
    delivery_start  TEXT NOT NULL,
    delivery_end    TEXT NOT NULL,
    book            TEXT NOT NULL,
    profit_centre   TEXT NOT NULL,
    status          TEXT NOT NULL       -- furthest lifecycle stage reached
);

CREATE TABLE IF NOT EXISTS confirmations (
    confirmation_id INTEGER PRIMARY KEY,
    trade_id        INTEGER NOT NULL REFERENCES trades(trade_id),
    confirmed_price     REAL NOT NULL,
    confirmed_quantity  REAL NOT NULL,
    received_date       TEXT NOT NULL,
    affirmed            INTEGER NOT NULL   -- 0/1
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id          INTEGER PRIMARY KEY,
    trade_id            INTEGER NOT NULL REFERENCES trades(trade_id),
    invoiced_amount     REAL NOT NULL,
    invoice_date        TEXT NOT NULL,
    settlement_due_date TEXT NOT NULL,
    settled_date        TEXT,              -- nullable
    settlement_status   TEXT NOT NULL       -- Pending / Settled / Failed
);
"""

LIFECYCLE_STAGES = [
    "Captured",
    "Enriched",
    "Validated",
    "Confirmed",
    "Allocated",
    "Invoiced",
    "Settled",
]


def get_connection(read_only=False):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if read_only and DB_PATH.exists():
        uri = f"file:{DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def reset_db():
    """Drops all tables — used only by the generator script."""
    conn = get_connection()
    conn.executescript(
        """
        DROP TABLE IF EXISTS invoices;
        DROP TABLE IF EXISTS confirmations;
        DROP TABLE IF EXISTS trades;
        DROP TABLE IF EXISTS counterparties;
        """
    )
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
