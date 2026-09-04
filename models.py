"""Pydantic request/response schemas."""

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


# --- quotes -----------------------------------------------------------------

class QuoteRequest(BaseModel):
    pickup: LatLng
    dropoff: LatLng
    product: str = "standard"


class FareBreakdown(BaseModel):
    base: float
    distance: float
    time: float
    surge_mult: float
    surge_amount: float
    tax: float
    total: float


class QuoteResponse(BaseModel):
    quote_id: str
    product: str
    currency: str            # "INR"
    distance_km: float
    duration_min: float
    breakdown: FareBreakdown
    expires_at: int          # epoch seconds


# --- bookings --------------------------------------------------------------

class BookingRequest(BaseModel):
    quote_id: str
    rider_id: str
    rider_name: str


class BookingResponse(BaseModel):
    booking_id: str
    quote_id: str
    rider_id: str
    rider_name: str
    currency: str            # "INR"
    total: float             # the locked fare
    created_ts: int


# --- drivers --------------------------------------------------------------

class HeartbeatRequest(BaseModel):
    driver_id: str
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    available: bool
