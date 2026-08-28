import os
import asyncpg
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if present; no-op in production (Railway injects env vars directly)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://voiceagent:voiceagent@localhost:5432/voiceagent",
)

_pool: asyncpg.Pool | None = None


async def init_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn():
    pool = await init_pool()
    async with pool.acquire() as conn:
        yield conn