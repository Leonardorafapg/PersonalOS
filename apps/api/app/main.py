import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  (registers every model)
from app.api import oauth, routes
from app.core import db as dbmod
from app.core.config import get_settings
from app.core.errors import AppError
from app.domains.identity.service import ensure_owner
from app.mcp.auth import McpAuth
from app.mcp.server import build_mcp

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    mcp = build_mcp()
    mcp_asgi = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if dbmod.engine.dialect.name == "sqlite":  # local dev convenience; Postgres uses Alembic
            dbmod.Base.metadata.create_all(dbmod.engine)
        with dbmod.SessionLocal() as db:
            ensure_owner(db)
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Personal OS API", version="1.0.0", lifespan=lifespan)
    # The web app talks to this API through its own origin (/api rewrite), so browsers don't need CORS for it.
    # CORS_ORIGINS restricts which browser origins may call the API directly; unset = any origin, no cookies.
    origins = get_settings().cors_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=bool(origins),
        allow_methods=["*"], allow_headers=["*"],
        expose_headers=["WWW-Authenticate", "Mcp-Session-Id"],
    )

    @app.exception_handler(HTTPException)
    async def http_exc(_: Request, exc: HTTPException):
        code = "UNAUTHORIZED" if exc.status_code == 401 else "ERROR"
        return JSONResponse({"ok": False, "error": {"code": code, "message": str(exc.detail)}}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return JSONResponse(
            {"ok": False, "error": {"code": "VALIDATION", "message": f"{loc}: {first.get('msg', 'invalid')}".strip(": ")}},
            status_code=422,
        )

    @app.exception_handler(AppError)
    async def app_exc(_: Request, exc: AppError):
        return JSONResponse({"ok": False, "error": exc.to_dict()}, status_code=exc.http_status)

    app.include_router(oauth.router)
    app.include_router(routes.router)
    # The MCP app answers /mcp; everything else it receives is a 404. Mounted last so API routes win.
    app.mount("/", McpAuth(mcp_asgi))
    return app


app = create_app()
