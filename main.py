"""FastAPI app: all routes plus the uvicorn entrypoint. Run with `python main.py`."""

import sqlite3
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query

import config
import db
from db import get_conn, now_ts
from fare import build_fare_breakdown, duration_min, road_distance_km
from models import (
    BookingRequest,
    BookingResponse,
    FareBreakdown,
    HeartbeatRequest,
    QuoteRequest,
    QuoteResponse,
)
from surge import cell_for, surge_multiplier, surge_stats


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()   # create tables if missing
    db.seed()      # sample Chennai/Bengaluru drivers so surge/quotes work at once
    yield


app = FastAPI(title="cab-fare microservice", lifespan=lifespan)


# --- quotes --------------------------------------------------------------------

@app.post("/quotes", response_model=QuoteResponse)
def create_quote(req: QuoteRequest) -> QuoteResponse:
    if req.product not in config.PRODUCTS:
        raise HTTPException(422, f"unknown product '{req.product}'")

    distance_km = road_distance_km(
        req.pickup.lat, req.pickup.lng, req.dropoff.lat, req.dropoff.lng
    )
    dur = duration_min(distance_km)
    cell = cell_for(req.pickup.lat, req.pickup.lng)
    mult = surge_multiplier(cell)
    breakdown = build_fare_breakdown(distance_km, dur, req.product, mult)

    quote_id = "qte-" + uuid.uuid4().hex[:12]
    created = now_ts()
    expires = created + config.QUOTE_TTL_SECONDS

    conn = get_conn()
    conn.execute(
        """INSERT INTO quotes (
               id, pickup_lat, pickup_lng, drop_lat, drop_lng, pickup_cell,
               product, distance_km, duration_min, base_fare, surge_mult,
               surge_amount, tax, total, status, created_ts, expires_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'HELD', ?, ?)""",
        (
            quote_id, req.pickup.lat, req.pickup.lng, req.dropoff.lat, req.dropoff.lng,
            cell, req.product, round(distance_km, 3), round(dur, 1),
            breakdown["base"], breakdown["surge_mult"], breakdown["surge_amount"],
            breakdown["tax"], breakdown["total"], created, expires,
        ),
    )
    conn.commit()
    conn.close()

    return QuoteResponse(
        quote_id=quote_id,
        product=req.product,
        currency=config.CURRENCY,
        distance_km=round(distance_km, 3),
        duration_min=round(dur, 1),
        breakdown=FareBreakdown(**breakdown),
        expires_at=expires,
    )


# --- bookings -----------------------------------------------------------------

@app.post("/bookings", response_model=BookingResponse, status_code=201)
def create_booking(req: BookingRequest) -> BookingResponse:
    """Double-booking-prevention pattern.

    The read -> check -> insert below runs inside a single `BEGIN IMMEDIATE`
    transaction, which takes the DB write lock up front, so it is serialized
    against any concurrent booking. The real guarantee, though, is the
    `bookings.quote_id UNIQUE` constraint: if two requests still race past the
    status check, only one INSERT can commit and the other raises
    `IntegrityError`. If the loser is the *same rider*, we treat the call as an
    idempotent retry and return their existing booking; otherwise it's a 409.

    Quote expiry is checked here, lazily — there is no background sweeper.
    """
    conn = get_conn()
    conn.isolation_level = None  # we drive BEGIN/COMMIT/ROLLBACK ourselves
    try:
        conn.execute("BEGIN IMMEDIATE")

        quote = conn.execute(
            "SELECT * FROM quotes WHERE id = ?", (req.quote_id,)
        ).fetchone()
        if quote is None:
            conn.execute("ROLLBACK")
            raise HTTPException(404, "quote not found")

        now = now_ts()
        bookable = quote["status"] == "HELD" and quote["expires_ts"] >= now

        if bookable:
            booking_id = "bkg-" + uuid.uuid4().hex[:12]
            try:
                conn.execute(
                    "INSERT INTO bookings "
                    "(id, quote_id, rider_id, rider_name, total, created_ts) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (booking_id, req.quote_id, req.rider_id, req.rider_name,
                     quote["total"], now),
                )
                conn.execute(
                    "UPDATE quotes SET status = 'CONSUMED' WHERE id = ?", (req.quote_id,)
                )
                conn.execute("COMMIT")
                return BookingResponse(
                    booking_id=booking_id,
                    quote_id=req.quote_id,
                    rider_id=req.rider_id,
                    rider_name=req.rider_name,
                    currency=config.CURRENCY,
                    total=quote["total"],
                    created_ts=now,
                )
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")  # lost the race; fall through
        else:
            conn.execute("ROLLBACK")

        # Not bookable, or we lost the INSERT race. If this same rider already
        # holds a booking for this quote, return it (idempotent retry).
        existing = conn.execute(
            "SELECT * FROM bookings WHERE quote_id = ?", (req.quote_id,)
        ).fetchone()
        if existing and existing["rider_id"] == req.rider_id:
            return BookingResponse(
                booking_id=existing["id"],
                quote_id=existing["quote_id"],
                rider_id=existing["rider_id"],
                rider_name=existing["rider_name"],
                currency=config.CURRENCY,
                total=existing["total"],
                created_ts=existing["created_ts"],
            )
        raise HTTPException(409, "quote is not bookable (expired, or already booked)")
    finally:
        conn.close()


@app.get("/bookings")
def list_bookings(rider_id: str = Query(...)) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id AS booking_id, quote_id, rider_id, rider_name, total, created_ts "
        "FROM bookings WHERE rider_id = ? ORDER BY created_ts DESC, id DESC",
        (rider_id,),
    ).fetchall()
    conn.close()
    return [{**dict(r), "currency": config.CURRENCY} for r in rows]


# --- drivers ----------------------------------------------------------------

@app.post("/drivers/heartbeat")
def driver_heartbeat(req: HeartbeatRequest) -> dict:
    conn = get_conn()
    conn.execute(
        """INSERT INTO drivers (id, lat, lng, available, last_heartbeat_ts)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               lat = excluded.lat,
               lng = excluded.lng,
               available = excluded.available,
               last_heartbeat_ts = excluded.last_heartbeat_ts""",
        (req.driver_id, req.lat, req.lng, int(req.available), now_ts()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "driver_id": req.driver_id, "cell": cell_for(req.lat, req.lng)}


# --- surge visibility ------------------------------------------------------

@app.get("/surge")
def surge(lat: float = Query(...), lng: float = Query(...)) -> dict:
    return surge_stats(cell_for(lat, lng))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
