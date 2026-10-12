"""ASGI application factory."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import commands as command_routes
from app.api.realtime import broadcaster
from app.api.routes import auth, files, queries, system
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.modules import load_modules

log = logging.getLogger("flow.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    broadcaster.start(asyncio.get_running_loop())
    yield
    broadcaster.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_json)
    load_modules()
    app = FastAPI(
        title="Workflow System API",
        version=settings.git_sha,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs" if settings.env != "prod" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "unexpected server error"}},
        )

    api = APIRouter(prefix="/api")
    api.include_router(system.router)
    api.include_router(auth.router)
    api.include_router(queries.router)
    api.include_router(files.router)
    api.include_router(command_routes.build_router())
    app.include_router(api)
    return app


app = create_app()
