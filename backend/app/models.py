from pydantic import BaseModel
from typing import Optional


class CheckAvailabilityRequest(BaseModel):
    party_size: int
    date: str          # YYYY-MM-DD
    time: str          # HH:MM (24h)
    restaurant_id: Optional[str] = None


class TableInfo(BaseModel):
    id: str
    label: str
    seats: int


class AlternativeSlot(BaseModel):
    time: str


class CheckAvailabilityResponse(BaseModel):
    available: bool
    matching_table: Optional[TableInfo] = None
    alternatives: list[AlternativeSlot] = []


class CreateReservationRequest(BaseModel):
    party_size: int
    date: str
    time: str
    guest_name: str
    caller_number: Optional[str] = None
    restaurant_id: Optional[str] = None


class CreateReservationResponse(BaseModel):
    success: bool
    reservation_id: Optional[str] = None
    table: Optional[str] = None
    confirmation_summary: Optional[str] = None
    error: Optional[str] = None
    alternatives: list[AlternativeSlot] = []


class ModifyReservationRequest(BaseModel):
    reservation_id: Optional[str] = None
    caller_number: Optional[str] = None
    new_date: Optional[str] = None
    new_time: Optional[str] = None
    new_party_size: Optional[int] = None
    restaurant_id: Optional[str] = None


class ModifyReservationResponse(BaseModel):
    success: bool
    reservation_id: Optional[str] = None
    updated_summary: Optional[str] = None
    error: Optional[str] = None
    alternatives: list[AlternativeSlot] = []


class LookupGuestRequest(BaseModel):
    caller_number: str
    restaurant_id: Optional[str] = None


class LookupGuestResponse(BaseModel):
    known: bool
    name: Optional[str] = None
    preference: Optional[str] = None
    last_reservation_id: Optional[str] = None


class RequestCallbackRequest(BaseModel):
    reason: str          # why the agent could not close it
    context: str         # what the guest actually asked for
    guest_name: Optional[str] = None
    caller_number: Optional[str] = None
    restaurant_id: Optional[str] = None


class RequestCallbackResponse(BaseModel):
    success: bool
    callback_id: Optional[str] = None
    message: Optional[str] = None