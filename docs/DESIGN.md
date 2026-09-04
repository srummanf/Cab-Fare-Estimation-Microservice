# Cab-Fare Microservice — Design

## Purpose
A minimal learning service that models the pricing path shared by ride-hailing
and delivery products: **quote → hold → book**, with dynamic (surge) pricing.
This is not production code — SQLite, single process, no auth / payments / routing.

## Domain model
- **Quote** — a priced trip estimate with a short TTL. Status `HELD` → `CONSUMED`.
  The price shown to a rider is a *promise* that expires.
- **Booking** — consumes exactly one quote and locks its total. `quote_id` is UNIQUE.
- **Driver** — a row refreshed by heartbeats; recent + available drivers are surge "supply".

## Request flow
1. `POST /quotes` — haversine distance × road factor → duration → base fare by
   product → surge multiplier for the pickup cell → tax → total. Row saved `HELD`,
   `expires_ts = now + QUOTE_TTL`.
2. `POST /bookings` — one `BEGIN IMMEDIATE` transaction: re-read the quote, check
   it is `HELD` and not expired, `INSERT` the booking, mark the quote `CONSUMED`,
   commit.
3. `GET /bookings?rider_id=` — that rider's bookings, newest first.
4. `POST /drivers/heartbeat` — upsert driver position + availability.
5. `GET /surge?lat=&lng=` — inspect demand / supply / ratio / multiplier for a cell.

## Fare math (fare.py)
All amounts in **INR**, rounded to whole rupees.
```
distance_km  = haversine(pickup, dropoff) * ROAD_FACTOR
duration_min = distance_km / AVG_SPEED_KMH * 60
subtotal     = base[product] + per_km[product]*distance_km + per_min[product]*duration_min
surge_amount = subtotal * (surge_mult - 1)
tax          = (subtotal + surge_amount) * TAX_RATE      # 5% GST
total        = subtotal + surge_amount + tax
```
Products (`config.PRODUCTS`): `standard` hatchback ₹50 + ₹14/km + ₹1.5/min,
`xl` SUV ₹90 + ₹20/km + ₹2/min, `premium` sedan ₹120 + ₹24/km + ₹2.5/min.

## Surge (surge.py)
- `cell   = (round(lat, PRECISION), round(lng, PRECISION))`
- `demand = quotes in this cell in the last SURGE_WINDOW minutes`
- `supply = available drivers in this cell with a heartbeat in the last DRIVER_FRESH seconds`
- `ratio  = demand / max(supply, 1)`
- bucket into `{1.0, 1.2, 1.5, 2.0}`; if the current hour is in `PEAK_HOURS`, bump one bucket.

## Concurrency / double-booking
The read → check → insert in `POST /bookings` runs inside `BEGIN IMMEDIATE`, so it
is serialized against any concurrent booking on the same DB. The real guarantee is
the `bookings.quote_id UNIQUE` constraint: if two requests still race, only one
`INSERT` wins and the loser catches `IntegrityError`. If the losing request is the
*same rider*, we return their existing booking (idempotent retry); otherwise `409`.

## Deliberate simplifications (also flagged in code)
- **Surge feedback loop** — demand counts *issued* quotes, so every `/quotes` call
  nudges surge upward, including quotes that never convert. Real pricing engines
  use rider-side demand signals (app opens, ride requests).
- **Distance** — real haversine, then `× ROAD_FACTOR` (1.3) as a stand-in for road
  routing. No traffic model; `AVG_SPEED_KMH` is a single constant 40, so a long
  intercity quote (Chennai→Bengaluru ≈ 380 km) still over-estimates the duration.
- **Cells** — lat/lng rounding produces longitude-dependent rectangles, not a real
  grid (production uses H3 / S2 hexes).
- **No riders / products tables** — `rider_id` and `rider_name` are free text
  supplied on each booking (no lookup); `product` is validated
  against `config.PRODUCTS`.
- SQLite, single uvicorn worker, `check_same_thread=False`, one connection per request.

## Seed data
`db.seed()` loads 11 sample drivers (`Suresh, Aman, Nikhil, Singh, George, Sara,
Manny` in the Chennai Central cell `13.08, 80.28`; `Nandini, Kalyani, Gurpreet,
Shyam` in the Bengaluru Majestic cell `12.98, 77.57`). `Manny` and `Shyam` are
off duty, so a Chennai pickup sees 6 available drivers, Bengaluru 3.

## Files
`config.py` · `db.py` · `fare.py` · `surge.py` · `models.py` · `main.py`
(`input.py` is a separate client helper.)

## Out of scope
Auth, payments, routing APIs, driver matching, tests, Docker, Alembic, Redis,
background workers, hysteresis, ML prediction, frontend.
