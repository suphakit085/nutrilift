"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, profile
from app.core.config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="NutriLift API",
    description="แชตบอทให้ความรู้ด้านโภชนาการสำหรับผู้ฝึกเวทเทรนนิ่ง (RAG + เครื่องคำนวณ)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(chat.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {
        "status": "ok",
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
    }
