from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crud import Draft, finish
from app.core.ctx import Ctx
from app.core.errors import AppError, validation
from app.core.security import hash_password, verify_password
from app.core.timeutil import get_tz
from app.domains.audit import service as audit
from app.domains.identity.models import User, UserPreferences
from app.domains.identity.schemas import Preferences, PreferencesPatch

log = logging.getLogger("personal_os")


# -- users ------------------------------------------------------------------

def ensure_owner(db: Session) -> User:
    """Create the single owner account on first boot from ADMIN_EMAIL / ADMIN_PASSWORD."""
    settings = get_settings()
    user = db.scalars(select(User).order_by(User.id)).first()
    if user:
        return user
    password = settings.admin_password
    if not password:
        if settings.is_production:
            raise RuntimeError("ADMIN_PASSWORD must be set in production to create the owner account")
        password = "admin"
        log.warning("ADMIN_PASSWORD not set; using the development password 'admin'")
    user = User(email=settings.admin_email.strip().lower(), name="Owner", password_hash=hash_password(password))
    db.add(user)
    db.flush()
    db.add(
        UserPreferences(
            user_id=user.id, timezone=settings.default_timezone, data=Preferences().model_dump(),
            created_by="system", updated_by="system",
        )
    )
    db.commit()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalars(select(User).where(User.email == email.strip().lower())).first()
    if user and verify_password(password, user.password_hash):
        return user
    return None


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError("UNAUTHORIZED", "Senha atual incorreta")
    user.password_hash = hash_password(new)
    user.token_version += 1  # signs out every other device / connector
    db.commit()


def revoke_all(db: Session, user: User) -> None:
    user.token_version += 1
    db.commit()


# -- preferences ------------------------------------------------------------

def get_prefs_row(ctx: Ctx) -> UserPreferences:
    if ctx._prefs_cache is not None:
        return ctx._prefs_cache[0]
    row = ctx.db.scalars(
        select(UserPreferences).where(UserPreferences.user_id == ctx.user_id, UserPreferences.deleted_at.is_(None))
    ).first()
    if row is None:
        row = UserPreferences(
            user_id=ctx.user_id, timezone=get_settings().default_timezone, data=Preferences().model_dump(),
            created_by="system", updated_by="system",
        )
        ctx.db.add(row)
        ctx.db.flush()
    ctx._prefs_cache = (row, Preferences.model_validate({**Preferences().model_dump(), **(row.data or {})}))
    return row


def get_prefs(ctx: Ctx) -> Preferences:
    get_prefs_row(ctx)
    return ctx._prefs_cache[1]


def prefs_out(ctx: Ctx) -> dict:
    row = get_prefs_row(ctx)
    return {"timezone": row.timezone, "version": row.version, **get_prefs(ctx).model_dump()}


def save_preferences(ctx: Ctx, patch: PreferencesPatch) -> dict:
    row = get_prefs_row(ctx)
    if patch.version is not None and patch.version != row.version:
        raise AppError(
            "STALE_VERSION",
            f"Preferences changed (you sent v{patch.version}, current v{row.version}). Re-read and retry.",
            details={"current_version": row.version},
        )
    d = Draft(row, False, audit.snapshot(row))
    sent = patch.model_fields_set - {"version"}
    if "timezone" in sent and patch.timezone:
        get_tz(patch.timezone)
        row.timezone = patch.timezone
    data = {**Preferences().model_dump(), **(row.data or {})}
    for k in sent:
        if k == "timezone":
            continue
        v = getattr(patch, k)
        if v is None:
            raise validation(f"{k} cannot be null", k)
        data[k] = [m.model_dump() if hasattr(m, "model_dump") else m for m in v] if isinstance(v, list) else v
    row.data = Preferences.model_validate(data).model_dump()  # validates cross-field values
    action = finish(ctx, d, "preferences", "Preferências")
    ctx.invalidate_prefs()
    return {"action": action, "preferences": prefs_out(ctx)}
