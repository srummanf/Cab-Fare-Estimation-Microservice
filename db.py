"""SQLite helpers: connection factory, schema, and a small driver seed."""

import sqlite3
import time

from config import DB_PATH


def now_ts() -> int:
    """One clock for the whole service: integer epoch seconds."""
    return int(time.time())


def get_conn() -> sqlite3.Connection:
    """A fresh connection per request. `check_same_thread=False` because
    uvicorn serves requests from a threadpool; we keep one worker so writes
    still serialize at the DB."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS drivers (
    id                TEXT PRIMARY KEY,
    lat               REAL    NOT NULL,
    lng               REAL    NOT NULL,
    available         INTEGER NOT NULL,
    last_heartbeat_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id           TEXT PRIMARY KEY,
    pickup_lat   REAL NOT NULL,
    pickup_lng   REAL NOT NULL,
    drop_lat     REAL NOT NULL,
    drop_lng     REAL NOT NULL,
    pickup_cell  TEXT NOT NULL,
    product      TEXT NOT NULL,
    distance_km  REAL NOT NULL,
    duration_min REAL NOT NULL,
    base_fare    REAL NOT NULL,
    surge_mult   REAL NOT NULL,
    surge_amount REAL NOT NULL,
    tax          REAL NOT NULL,
    total        REAL NOT NULL,
    status       TEXT NOT NULL,          -- HELD | CONSUMED
    created_ts   INTEGER NOT NULL,
    expires_ts   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quotes_cell_created ON quotes (pickup_cell, created_ts);

CREATE TABLE IF NOT EXISTS bookings (
    id         TEXT PRIMARY KEY,
    quote_id   TEXT NOT NULL UNIQUE,     -- one booking per quote: stops double-book
    rider_id   TEXT NOT NULL,
    rider_name TEXT NOT NULL,
    total      REAL NOT NULL,
    created_ts INTEGER NOT NULL
);
"""


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def seed() -> None:
    """Insert sample drivers once, so /surge and /quotes return sensible numbers
    on a fresh DB. Seven sit in the Chennai Central cell (13.08, 80.28), four in
    the Bengaluru Majestic cell (12.98, 77.57) — so a Chennai pickup sees supply,
    and a Bengaluru dropoff has drivers waiting too."""
    conn = get_conn()
    if conn.execute("SELECT COUNT(*) AS n FROM drivers").fetchone()["n"] == 0:
        ts = now_ts()
        drivers = [
            # id             lat       lng     available
            ("drv-suresh",   13.0826, 80.2763, 1, ts),   # Chennai (near Central)
            ("drv-aman",     13.0800, 80.2800, 1, ts),
            ("drv-nikhil",   13.0840, 80.2780, 1, ts),
            ("drv-singh",    13.0790, 80.2820, 1, ts),
            ("drv-george",   13.0810, 80.2760, 1, ts),
            ("drv-sara",     13.0770, 80.2790, 1, ts),
            ("drv-manny",    13.0830, 80.2770, 0, ts),   # in-cell but off duty
            ("drv-nandini",  12.9780, 77.5710, 1, ts),   # Bengaluru (near Majestic)
            ("drv-kalyani",  12.9800, 77.5730, 1, ts),
            ("drv-gurpreet", 12.9760, 77.5690, 1, ts),
            ("drv-shyam",    12.9820, 77.5720, 0, ts),   # in-cell but off duty
        ]
        conn.executemany(
            "INSERT INTO drivers (id, lat, lng, available, last_heartbeat_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            drivers,
        )
        conn.commit()
    conn.close()
