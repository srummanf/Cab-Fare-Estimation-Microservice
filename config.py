"""Tunable constants for the cab-fare service. No logic here."""

# Where the SQLite file lives (created on first run).
DB_PATH = "cabfare.db"

# All money is in Indian Rupees (INR).
CURRENCY = "INR"

# Fare rates per product, in INR. `base` is the flat drop fee; the rest marginal.
PRODUCTS = {
    "standard": {"base": 50.0,  "per_km": 14.0, "per_min": 1.5},   # hatchback
    "xl":       {"base": 90.0,  "per_km": 20.0, "per_min": 2.0},   # SUV / 6-seater
    "premium":  {"base": 120.0, "per_km": 24.0, "per_min": 2.5},   # sedan
}
DEFAULT_PRODUCT = "standard"

TAX_RATE = 0.05         # 5% GST on cab rides; applied to (subtotal + surge_amount)
AVG_SPEED_KMH = 40.0     # single constant, no traffic model (rough Indian blended speed)
ROAD_FACTOR = 1.30       # haversine is straight-line; roads detour ~30% longer

QUOTE_TTL_SECONDS = 120        # how long a quoted price is honoured
SURGE_WINDOW_MINUTES = 10      # look-back window for demand
DRIVER_FRESH_SECONDS = 180     # a heartbeat older than this doesn't count as supply

CELL_PRECISION = 2                       # decimal places for the surge grid
PEAK_HOURS = {7, 8, 9, 17, 18, 19}      # local hours that bump surge one bucket
SURGE_BUCKETS = [1.0, 1.2, 1.5, 2.0]    # allowed multipliers, ascending
