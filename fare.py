"""Distance, duration, and the fare breakdown. Pure functions, no I/O."""

import math

from config import AVG_SPEED_KMH, DEFAULT_PRODUCT, PRODUCTS, ROAD_FACTOR, TAX_RATE

EARTH_RADIUS_KM = 6371.0088


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two lat/lng points. Real, not mocked."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def road_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine scaled by ROAD_FACTOR — a stand-in for real road routing."""
    return haversine(lat1, lng1, lat2, lng2) * ROAD_FACTOR


def duration_min(distance_km: float) -> float:
    """km / avg_speed, expressed in minutes. No traffic model."""
    return distance_km / AVG_SPEED_KMH * 60.0


def build_fare_breakdown(distance_km: float, duration_min: float,
                         product: str, surge_mult: float) -> dict:
    rates = PRODUCTS.get(product, PRODUCTS[DEFAULT_PRODUCT])

    base = rates["base"]
    distance_cost = rates["per_km"] * distance_km
    time_cost = rates["per_min"] * duration_min
    subtotal = base + distance_cost + time_cost

    surge_amount = subtotal * (surge_mult - 1.0)
    tax = (subtotal + surge_amount) * TAX_RATE
    total = subtotal + surge_amount + tax

    # Indian cab fares are quoted in whole rupees.
    return {
        "base": round(base),
        "distance": round(distance_cost),
        "time": round(time_cost),
        "surge_mult": surge_mult,
        "surge_amount": round(surge_amount),
        "tax": round(tax),
        "total": round(total),
    }
