"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import exists, select, text
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.api import auth, chat, food_log, foods, profile
from app.core.config import check_production_settings, settings
from app.db.models import Chunk, Food
from app.db.session import engine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Raises in production (Render/Railway or ENVIRONMENT=production) when the
    # JWT secret or Gemini key is still a placeholder; warns elsewhere.
    check_production_settings(settings)
    yield


app = FastAPI(
    title="NutriLift API",
    description="แชตบอทให้ความรู้ด้านโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง (RAG + เครื่องคำนวณ)",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Retry-After is not a CORS-safelisted response header, so without this the
    # frontend cannot read the 429 wait time from a different origin.
    # X-Consent-Required travels with a 403 and tells the client to send the
    # user to the consent screen. The frontend is a different origin, so without
    # listing it here the browser hides it and the client is left guessing from
    # the Thai message text.
    expose_headers=["Retry-After", "X-Consent-Required", "X-Email-Verification-Required"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(foods.router)
app.include_router(food_log.router)
app.include_router(chat.router)


async def database_unavailable(_: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).error("Database operation unavailable (%s)", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "ระบบฐานข้อมูลไม่พร้อมชั่วคราว กรุณาลองใหม่อีกครั้งในสักครู่"},
        headers={"Retry-After": "10", "Cache-Control": "no-store"},
    )


for database_error in (OperationalError, InterfaceError, DisconnectionError, PoolTimeoutError):
    app.add_exception_handler(database_error, database_unavailable)


def readiness_checks() -> dict[str, bool]:
    checks = {
        "database": False,
        "knowledge": False,
        "email_configured": settings.email_delivery_configured,
    }
    try:
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            connection.execute(select(1))
            checks["database"] = True
            checks["knowledge"] = bool(
                connection.scalar(select(exists().where(Chunk.id.is_not(None))))
            ) and bool(connection.scalar(select(exists().where(Food.id.is_not(None)))))
    except SQLAlchemyError:
        logging.getLogger(__name__).warning("Readiness dependency check failed")
    return checks


@app.get("/ready", tags=["meta"])
def ready() -> JSONResponse:
    checks = readiness_checks()
    available = all(checks.values())
    return JSONResponse(
        status_code=200 if available else 503,
        content={"status": "ready" if available else "unavailable", "checks": checks},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
    }
