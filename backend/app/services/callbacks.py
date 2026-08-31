import asyncpg

from app.services.guests import lookup_guest_by_phone


async def create_callback(
    conn: asyncpg.Connection,
    restaurant_id: str,
    reason: str,
    context: str,
    caller_number: str | None,
    guest_name: str | None,
    vapi_call_id: str | None = None,
):
    """Records a request the agent couldn't close on the call.

    Deliberately tolerant: a callback must never fail to save. If the guest
    lookup errors or the caller is unknown, we still write the row — losing
    the guest's request is a worse outcome than an unlinked record.
    """
    guest_id = None
    resolved_name = guest_name

    if caller_number:
        try:
            guest = await lookup_guest_by_phone(conn, restaurant_id, caller_number)
            if guest:
                guest_id = guest["id"]
                resolved_name = resolved_name or guest["name"]
        except Exception:  # noqa: BLE001
            pass

    row = await conn.fetchrow(
        """
        insert into callbacks
            (restaurant_id, guest_id, caller_number, guest_name, reason, context, vapi_call_id)
        values ($1, $2, $3, $4, $5, $6, $7)
        returning id
        """,
        restaurant_id,
        guest_id,
        caller_number,
        resolved_name,
        reason,
        context,
        vapi_call_id,
    )

    return {
        "success": True,
        "callback_id": str(row["id"]),
        "message": (
            "Callback logged. Tell the guest the team has their request and will "
            "call them back, then confirm the number to reach them on."
        ),
    }