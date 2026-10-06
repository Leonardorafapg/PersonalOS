from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core import db as dbmod
from app.core.config import get_settings
from app.core.runner import run
from app.core.security import decode_token
from app.domains.identity.models import User


def user_from_token(token: str | None) -> User | None:
    if not token:
        return None
    claims = decode_token(token)
    if not claims:
        return None
    with dbmod.SessionLocal() as db:
        user = db.get(User, int(claims["sub"]))
        if user is None or user.token_version != claims["tv"]:
            return None
        db.expunge(user)
        return user


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(get_settings().session_cookie_name)


def current_user(request: Request) -> User:
    user = user_from_token(extract_token(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def respond(result: tuple[int, dict]) -> JSONResponse:
    status, env = result
    return JSONResponse(jsonable_encoder(env), status_code=status)


def read(user: User, tool: str, fn: Callable[[Any], Any]) -> JSONResponse:
    return respond(run(user.id, "manual", "ui", tool, fn, write=False))


def write(user: User, tool: str, fn: Callable[[Any], Any], dry_run: bool = False) -> JSONResponse:
    return respond(run(user.id, "manual", "ui", tool, fn, write=True, dry_run=dry_run))


def first_result(data: dict, key: str = "results") -> dict:
    return data[key][0]
