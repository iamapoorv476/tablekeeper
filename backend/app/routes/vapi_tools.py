import time
import logging
from fastapi import APIRouter, Request

from app.db import get_conn
from app.models import (
    CheckAvailabilityRequest,
    CreateReservationRequest,
    ModifyReservationRequest,
    LookupGuestRequest,
    RequestCallbackRequest,
)
from app.services.availability import (
    find_smallest_fitting_table,
    find_alternatives,
    DEFAULT_RESTAURANT_ID,
)
from app.services.reservations import create_reservation, modify_reservation
from app.services.guests import lookup_guest_by_phone, get_last_reservation_id
from app.services.callbacks import create_callback

router = APIRouter()
logger = logging.getLogger("voice-agent")


@router.post("/tools/check_availability")
async def check_availability_endpoint(payload: CheckAvailabilityRequest):
    restaurant_id = payload.restaurant_id or DEFAULT_RESTAURANT_ID
    async with get_conn() as conn:
        table = await find_smallest_fitting_table(
            conn, restaurant_id, payload.party_size, payload.date, payload.time
        )
        if table:
            return {
                "available": True,
                "matching_table": {"id": str(table["id"]), "label": table["label"], "seats": table["seats"]},
                "alternatives": [],
            }
        alternatives = await find_alternatives(
            conn, restaurant_id, payload.party_size, payload.date, payload.time
        )
        return {
            "available": False,
            "matching_table": None,
            "alternatives": [{"time": t} for t in alternatives],
        }


@router.post("/tools/create_reservation")
async def create_reservation_endpoint(payload: CreateReservationRequest):
    restaurant_id = payload.restaurant_id or DEFAULT_RESTAURANT_ID
    async with get_conn() as conn:
        return await create_reservation(
            conn,
            restaurant_id,
            payload.party_size,
            payload.date,
            payload.time,
            payload.guest_name,
            payload.caller_number,
        )


@router.post("/tools/modify_reservation")
async def modify_reservation_endpoint(payload: ModifyReservationRequest):
    restaurant_id = payload.restaurant_id or DEFAULT_RESTAURANT_ID
    async with get_conn() as conn:
        return await modify_reservation(
            conn,
            restaurant_id,
            payload.reservation_id,
            payload.caller_number,
            payload.new_date,
            payload.new_time,
            payload.new_party_size,
        )


@router.post("/tools/lookup_guest")
async def lookup_guest_endpoint(payload: LookupGuestRequest):
    restaurant_id = payload.restaurant_id or DEFAULT_RESTAURANT_ID
    async with get_conn() as conn:
        guest = await lookup_guest_by_phone(conn, restaurant_id, payload.caller_number)
        if guest is None:
            return {"known": False, "name": None, "preference": None, "last_reservation_id": None}
        last_id = await get_last_reservation_id(conn, guest["id"])
        return {
            "known": True,
            "name": guest["name"],
            "preference": guest["preferences"],
            "last_reservation_id": last_id,
        }

@router.post("/tools/request_callback")
async def request_callback_endpoint(payload: RequestCallbackRequest):
    """The no-dead-ends path. Anything the agent can't close on the call gets
    written here with enough context for a human to pick it up cold."""
    restaurant_id = payload.restaurant_id or DEFAULT_RESTAURANT_ID
    async with get_conn() as conn:
        return await create_callback(
            conn,
            restaurant_id,
            payload.reason,
            payload.context,
            payload.caller_number,
            payload.guest_name,
        )


# ---------------------------------------------------------------------------
# Vapi webhook — single URL, dispatches on function name inside the payload.
#
# IMPORTANT: as of the current Vapi API, each entry in toolCallList carries
# "name" and "arguments" directly (e.g. {"id": ..., "name": "get_weather",
# "arguments": {...}}) — NOT nested under a "function" key as in classic
# OpenAI-style function calling. We check the top-level shape first and fall
# back to a nested "function" key for safety.
# ---------------------------------------------------------------------------

TOOL_DISPATCH = {
    "check_availability": check_availability_endpoint,
    "create_reservation": create_reservation_endpoint,
    "modify_reservation": modify_reservation_endpoint,
    "lookup_guest": lookup_guest_endpoint,
    "request_callback": request_callback_endpoint,
}

MODEL_MAP = {
    "check_availability": CheckAvailabilityRequest,
    "create_reservation": CreateReservationRequest,
    "modify_reservation": ModifyReservationRequest,
    "lookup_guest": LookupGuestRequest,
    "request_callback": RequestCallbackRequest,
}


def _extract_name_and_args(tool_call: dict):
    if "name" in tool_call:
        return tool_call.get("name"), tool_call.get("arguments", {}) or {}
    fn = tool_call.get("function", {}) or {}
    return fn.get("name"), fn.get("arguments", {}) or {}


@router.post("/vapi/tools")
async def vapi_tools_webhook(request: Request):
    body = await request.json()
    message = body.get("message", {})

    if message.get("type") == "status-update" and message.get("status") == "in-progress":
        call = message.get("call", {}) or {}
        async with get_conn() as conn:
            await conn.execute(
                """
                insert into call_logs (vapi_call_id, restaurant_id, caller_number, started_at)
                values ($1, $2, $3, now())
                on conflict do nothing
                """,
                call.get("id"),
                DEFAULT_RESTAURANT_ID,
                (call.get("customer") or {}).get("number"),
            )
        return {"results": []}

    if message.get("type") != "tool-calls":
        return {"results": []}

    call = message.get("call", {}) or {}
    caller_number = (call.get("customer") or {}).get("number")
    vapi_call_id = call.get("id")

    results = []
    for tool_call in message.get("toolCallList", []):
        tool_call_id = tool_call.get("id")
        name, args = _extract_name_and_args(tool_call)
        args = dict(args)

        model_cls = MODEL_MAP.get(name)
        if caller_number and model_cls and "caller_number" in model_cls.__fields__:
            args.setdefault("caller_number", caller_number)

        start = time.perf_counter()
        result_payload = {"error": f"unknown tool {name}"}
        try:
            if name in TOOL_DISPATCH:
                parsed = model_cls(**args)
                result_payload = await TOOL_DISPATCH[name](parsed)
        except Exception as exc:  # noqa: BLE001
            logger.exception("tool call failed: %s", name)
            result_payload = {"error": str(exc)}
        latency_ms = int((time.perf_counter() - start) * 1000)

        logger.info("tool=%s latency_ms=%d call_id=%s", name, latency_ms, vapi_call_id)

        results.append({"toolCallId": tool_call_id, "result": str(result_payload)})

    return {"results": results}