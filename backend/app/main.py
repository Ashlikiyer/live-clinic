from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.db.session import get_sessionmaker
from app.providers.base import Providers
from app.providers.factory import build_providers
from app.repositories.calls import CallStore, SqlCallStore
from app.routers import call_ws, health, sessions


def create_app(store: CallStore | None = None, providers: Providers | None = None) -> FastAPI:
    """Build the app. Tests pass an in-memory store and fake providers."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient() as client:
            app.state.store = store or SqlCallStore(get_sessionmaker())
            app.state.providers = providers or build_providers(settings, client)
            yield

    app = FastAPI(title="Live Clinic Desk API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(call_ws.router)
    return app


app = create_app()
