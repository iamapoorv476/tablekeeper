import asyncpg


async def lookup_guest_by_phone(conn: asyncpg.Connection, restaurant_id: str, phone_number: str):
    return await conn.fetchrow(
        "select id, name, preferences from guests where restaurant_id = $1 and phone_number = $2",
        restaurant_id,
        phone_number,
    )


async def get_last_reservation_id(conn: asyncpg.Connection, guest_id: str):
    row = await conn.fetchrow(
        """
        select id from reservations
        where guest_id = $1
        order by created_at desc
        limit 1
        """,
        guest_id,
    )
    return str(row["id"]) if row else None


async def get_or_create_guest(
    conn: asyncpg.Connection, restaurant_id: str, phone_number: str, name: str
):
    """Used by create_reservation: if the caller isn't in guests yet, add them
    so the next call can recognize them. Never overwrites an existing name."""
    row = await lookup_guest_by_phone(conn, restaurant_id, phone_number)
    if row is not None:
        return row["id"]

    row = await conn.fetchrow(
        """
        insert into guests (restaurant_id, phone_number, name)
        values ($1, $2, $3)
        on conflict (restaurant_id, phone_number) do update set name = excluded.name
        returning id
        """,
        restaurant_id,
        phone_number,
        name,
    )
    return row["id"]