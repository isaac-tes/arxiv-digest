"""FastAPI app factory for the digest service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import auth, config, digest, removed, score, zotero
from .security import access_guard
from .settings import DEFAULT_JWT_SECRET, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_remote and settings.jwt_secret == DEFAULT_JWT_SECRET:
        raise RuntimeError("Remote mode needs a real DIGEST_JWT_SECRET (e.g. `openssl rand -hex 32`).")
    app = FastAPI(
        title="arXiv Digest API",
        version="0.1.0",
        description="Shared scoring/fetch backend for the arXiv digest mobile apps.",
        lifespan=lifespan,
    )

    # Starlette runs the last-added middleware first: CORS, then the guard.
    app.middleware("http")(access_guard)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(auth.router)
    app.include_router(digest.router)
    app.include_router(removed.router)
    app.include_router(score.router)
    app.include_router(config.router)
    app.include_router(zotero.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": settings.mode}

    return app


app = create_app()
