"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, food_log, foods, profile
from app.core.config import check_production_settings, settings

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
    expose_headers=["Retry-After", "X-Consent-Required"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(foods.router)
app.include_router(food_log.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
    }
