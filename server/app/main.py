"""FastAPI app factory for the digest service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import auth, config, digest, feedback, lists, score, zotero
from .settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="arXiv Digest API",
        version="0.1.0",
        description="Shared scoring/fetch backend for the arXiv digest mobile apps.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(digest.router)
    app.include_router(score.router)
    app.include_router(config.router)
    app.include_router(lists.router)
    app.include_router(feedback.router)
    app.include_router(zotero.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": settings.mode}

    return app


app = create_app()
