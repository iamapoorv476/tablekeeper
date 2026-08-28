import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db import init_pool, close_pool
from app.routes.vapi_tools import router as tools_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Voice Reservation Agent", lifespan=lifespan)
app.include_router(tools_router)


@app.get("/health")
async def health():
    return {"status": "ok"}