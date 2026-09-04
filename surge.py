"""Surge pricing: turn recent demand vs. available supply into a multiplier."""

import datetime

from config import (
    CELL_PRECISION,
    DRIVER_FRESH_SECONDS,
    PEAK_HOURS,
    SURGE_BUCKETS,
    SURGE_WINDOW_MINUTES,
)
from db import get_conn, now_ts


def cell_for(lat: float, lng: float) -> str:
    """A coarse grid square, e.g. '37.77,-122.42'. Rounding, not a real geo grid."""
    return f"{round(lat, CELL_PRECISION)},{round(lng, CELL_PRECISION)}"


def _bucket(ratio: float) -> float:
    if ratio <= 1.0:
        return SURGE_BUCKETS[0]   # 1.0
    if ratio <= 2.0:
        return SURGE_BUCKETS[1]   # 1.2
    if ratio <= 3.0:
        return SURGE_BUCKETS[2]   # 1.5
    return SURGE_BUCKETS[3]       # 2.0


def _bump_one_bucket(mult: float) -> float:
    i = SURGE_BUCKETS.index(mult)
    return SURGE_BUCKETS[min(i + 1, len(SURGE_BUCKETS) - 1)]


def surge_stats(cell: str) -> dict:
    """Everything behind the multiplier, for the /surge visibility endpoint."""
    now = now_ts()
    conn = get_conn()

    # demand: quotes issued in this cell inside the look-back window.
    # SIMPLIFICATION: counting issued quotes means every /quotes call nudges
    # surge upward, even quotes that never convert to a booking. A real pricing
    # engine measures rider-side demand (app opens, ride requests) instead.
    window_start = now - SURGE_WINDOW_MINUTES * 60
    demand = conn.execute(
        "SELECT COUNT(*) AS n FROM quotes WHERE pickup_cell = ? AND created_ts >= ?",
        (cell, window_start),
    ).fetchone()["n"]

    # supply: available drivers with a fresh heartbeat, then filtered to this cell.
    fresh_since = now - DRIVER_FRESH_SECONDS
    drivers = conn.execute(
        "SELECT lat, lng FROM drivers WHERE available = 1 AND last_heartbeat_ts >= ?",
        (fresh_since,),
    ).fetchall()
    conn.close()
    supply = sum(1 for d in drivers if cell_for(d["lat"], d["lng"]) == cell)

    ratio = demand / max(supply, 1)
    peak = datetime.datetime.now().hour in PEAK_HOURS

    multiplier = _bucket(ratio)
    if peak:
        multiplier = _bump_one_bucket(multiplier)

    return {
        "cell": cell,
        "demand": demand,
        "supply": supply,
        "ratio": round(ratio, 2),
        "peak": peak,
        "multiplier": multiplier,
    }


def surge_multiplier(cell: str) -> float:
    return surge_stats(cell)["multiplier"]
