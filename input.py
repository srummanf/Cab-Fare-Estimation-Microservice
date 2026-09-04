"""Hardcoded trip input + a detailed estimate writer.

Edit the constants below, then run:

    python input.py

It geocodes the two addresses, asks the running service (`python main.py`) for a
quote (and optionally a booking), prints a detailed breakdown, and writes the
same report to  estimate/estimate.txt.
"""

import datetime
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import config

try:  # so the rupee sign prints on a Windows console too
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# --- edit these --------------------------------------------------------------
PICKUP_ADDRESS = "Chennai Central Railway Station, Chennai, Tamil Nadu"
DROP_ADDRESS = "Kempegowda Bus Station, Bengaluru, Karnataka"

PICKUP_LATLNG = None      # e.g. (13.0827, 80.2763) -> used as-is, no geocoding
DROP_LATLNG = None        # e.g. (12.9776, 77.5713)

PRODUCT = "standard"      # standard | xl | premium
RIDER_ID = "rider-1"
RIDER_NAME = "Rohan Mehta"

API_URL = "http://127.0.0.1:8000"
BOOK = False              # True -> also POST /bookings for the quote

OUT_DIR = "estimate"
OUT_FILE = "estimate.txt"
# ---------------------------------------------------------------------------

WIDTH = 80


# --- geocoding --------------------------------------------------------------

def geocode(address: str) -> tuple[float, float]:
    from geopy.geocoders import Nominatim

    geo = Nominatim(user_agent="cab-fare-microservice-demo")
    loc = geo.geocode(address)
    if loc is None:
        raise SystemExit(f"could not geocode: {address!r}")
    return round(loc.latitude, 6), round(loc.longitude, 6)


def resolve(address, override) -> tuple[float, float, str]:
    if override is not None:
        return float(override[0]), float(override[1]), "hardcoded lat/lng"
    lat, lng = geocode(address)
    return lat, lng, "geocoded via OpenStreetMap Nominatim"


# --- HTTP ------------------------------------------------------------------

def _request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        API_URL + path, data=data,
        headers={"content-type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach {API_URL} — is `python main.py` running? ({e.reason})")


def get(path: str) -> tuple[int, dict]:
    return _request("GET", path)


def post(path: str, payload: dict) -> tuple[int, dict]:
    return _request("POST", path, payload)


# --- formatting helpers --------------------------------------------------

def _rule(ch: str = "-") -> str:
    return ch * WIDTH


def _section(title: str, endpoint: str = "") -> str:
    head = title
    if endpoint:
        head = f"{title}{endpoint:>{WIDTH - len(title)}}"
    return f"\n{_rule()}\n{head}\n{_rule()}"


def _money(x: float) -> str:
    return f"₹{round(x):>9,}"


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} m" if h else f"{m} m"


def _clock(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def _row(label: str, amount: float, note: str = "") -> str:
    s = f"  {label:<20}{_money(amount)}"
    return f"{s}   {note}" if note else s


# --- the report --------------------------------------------------------

def build_report(pickup, drop, quote, surge, booking) -> str:
    rates = config.PRODUCTS[quote["product"]]
    b = quote["breakdown"]
    dist_km = quote["distance_km"]
    dur_min = quote["duration_min"]
    straight_km = round(dist_km / config.ROAD_FACTOR, 3)
    subtotal = b["base"] + b["distance"] + b["time"]
    taxable = subtotal + b["surge_amount"]
    peak_hours = ", ".join(f"{h:02d}:00" for h in sorted(config.PEAK_HOURS))
    now = datetime.datetime.now().timestamp()

    L: list[str] = []
    L.append(_rule("="))
    L.append("CAB FARE ESTIMATE".center(WIDTH))
    L.append(_rule("="))
    calls = "geocode  ->  POST /quotes  ->  GET /surge"
    if booking is not None:
        calls += "  ->  POST /bookings"
    L.append(f"Generated : {_clock(now)}  (local time)")
    L.append(f"Service   : {API_URL}")
    L.append(f"Currency  : {quote['currency']}  (all amounts rounded to whole rupees)")
    L.append(f"Calls     : {calls}")

    # --- trip ---
    L.append(_section("TRIP", "geopy -> OpenStreetMap"))
    L.append(f"Pickup    : {PICKUP_ADDRESS}")
    L.append(f"            lat/lng {pickup[0]:.6f}, {pickup[1]:.6f}   ({pickup[2]})")
    L.append(f"            surge cell {surge['cell']}  "
             f"(lat/lng rounded to {config.CELL_PRECISION} decimals)")
    L.append(f"Dropoff   : {DROP_ADDRESS}")
    L.append(f"            lat/lng {drop[0]:.6f}, {drop[1]:.6f}   ({drop[2]})")
    L.append(f"Product   : {quote['product']}   "
             f"(₹{rates['base']:.0f} base + ₹{rates['per_km']:.0f}/km + ₹{rates['per_min']:.1f}/min)")

    # --- distance & time ---
    L.append(_section("DISTANCE & TIME", "POST /quotes"))
    L.append(f"  Straight-line distance : {straight_km:>10.3f} km")
    L.append( "                           great-circle (haversine) between the two points")
    L.append(f"  Road factor            : x{config.ROAD_FACTOR:.2f}")
    L.append( "                           flat allowance for road detours — this service has")
    L.append( "                           no maps/routing API, so it does not trace real roads")
    L.append(f"  Road distance (billed) : {dist_km:>10.3f} km")
    L.append(f"  Assumed average speed  : {config.AVG_SPEED_KMH:>10.0f} km/h  (one constant, no live traffic)")
    L.append(f"  Estimated duration     : {dur_min:>10.1f} min   (~{_hm(dur_min)})")
    L.append( "                           = road distance / average speed")

    # --- fare ---
    L.append(_section(f"FARE BREAKDOWN  ({quote['currency']})", "POST /quotes"))
    L.append(_row("Base fare", b["base"], f"flat drop charge for '{quote['product']}'"))
    L.append(_row("Distance charge", b["distance"],
                  f"₹{rates['per_km']:.0f}/km x {dist_km:.3f} km"))
    L.append(_row("Time charge", b["time"],
                  f"₹{rates['per_min']:.1f}/min x {dur_min:.1f} min"))
    L.append(f"  {'':<20}{'-' * 10}")
    L.append(_row("Subtotal", subtotal, "base + distance + time"))
    L.append(_row("Surge", b["surge_amount"],
                  f"subtotal x (x{b['surge_mult']:.2f} - 1) — see SURGE below"))
    L.append(f"  {'':<20}{'-' * 10}")
    L.append(_row("Taxable amount", taxable))
    L.append(_row(f"GST @ {config.TAX_RATE * 100:.0f}%", b["tax"], "government tax on the ride"))
    L.append(f"  {'':<20}{'=' * 10}")
    L.append(_row("TOTAL FARE", b["total"]))
    L.append(f"  {'':<20}{'=' * 10}")

    # --- surge ---
    L.append(_section("SURGE PRICING", "GET /surge"))
    L.append(f"  Pickup cell : {surge['cell']}")
    L.append(f"  Demand      : {surge['demand']}")
    L.append(f"                quotes created in this cell in the last "
             f"{config.SURGE_WINDOW_MINUTES} minutes")
    L.append(f"  Supply      : {surge['supply']}")
    L.append(f"                available drivers in this cell whose last heartbeat is")
    L.append(f"                within {config.DRIVER_FRESH_SECONDS} seconds")
    L.append(f"  Ratio       : {surge['ratio']}   (demand / max(supply, 1))")
    L.append(f"  Peak hour   : {'yes' if surge['peak'] else 'no'}   (peak hours: {peak_hours})")
    L.append(f"  Multiplier  : x{surge['multiplier']:.2f}")
    L.append(f"                ratio bucketed to one of {config.SURGE_BUCKETS};")
    L.append(f"                bumped one bucket during peak hours")

    # --- quote ---
    ttl_left = int(quote["expires_at"] - now)
    L.append(_section("QUOTE", "POST /quotes"))
    L.append(f"  Quote ID    : {quote['quote_id']}")
    L.append(f"  Status      : HELD   (this price is locked until it expires or is booked)")
    L.append(f"  Expires at  : {_clock(quote['expires_at'])}   "
             f"(~{ttl_left}s left; TTL {config.QUOTE_TTL_SECONDS}s)")
    L.append( "  Note        : after expiry you must request a fresh quote; the price")
    L.append( "                (especially surge) may then be different")

    # --- booking ---
    L.append(_section("BOOKING", "POST /bookings"))
    if booking is None:
        L.append(f"  Not requested.  Set  BOOK = True  in input.py to book this quote")
        L.append(f"  as rider '{RIDER_NAME}' ({RIDER_ID}).")
    else:
        code, body = booking
        if "booking_id" in body:
            L.append(f"  Booking ID  : {body['booking_id']}")
            L.append(f"  Rider       : {body['rider_name']}   ({body['rider_id']})")
            L.append(f"  Fare locked : ₹{round(body['total']):,}   "
                     f"guaranteed regardless of later surge")
            L.append(f"  Booked at   : {_clock(body['created_ts'])}")
            L.append(f"  HTTP status : {code}   (201 = created)")
        else:
            L.append(f"  Booking failed — HTTP {code}: {json.dumps(body)}")

    L.append(_rule("="))
    return "\n".join(L)


def main() -> None:
    pickup = resolve(PICKUP_ADDRESS, PICKUP_LATLNG)
    drop = resolve(DROP_ADDRESS, DROP_LATLNG)

    status, quote = post("/quotes", {
        "pickup": {"lat": pickup[0], "lng": pickup[1]},
        "dropoff": {"lat": drop[0], "lng": drop[1]},
        "product": PRODUCT,
    })
    if status != 200:
        raise SystemExit(f"POST /quotes -> {status}: {json.dumps(quote)}")

    _, surge = get(f"/surge?lat={pickup[0]}&lng={pickup[1]}")

    booking = None
    if BOOK:
        booking = post("/bookings", {
            "quote_id": quote["quote_id"],
            "rider_id": RIDER_ID,
            "rider_name": RIDER_NAME,
        })

    report = build_report(pickup, drop, quote, surge, booking)
    print(report)

    out_dir = Path(OUT_DIR)
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / OUT_FILE
    out_path.write_text(report + "\n", encoding="utf-8")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
