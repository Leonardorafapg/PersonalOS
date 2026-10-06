from typing import Any

STATUS = {
    "VALIDATION": 422,
    "NOT_FOUND": 404,
    "STALE_VERSION": 409,
    "CONFLICT_OVERLAP": 409,
    "CONFLICT_FIXED_EVENT": 409,
    "PAST_DATE": 422,
    "CONFIRMATION_REQUIRED": 412,
    "UNAUTHORIZED": 401,
    "UNDO_NOT_POSSIBLE": 409,
    "INTERNAL": 500,
}


class AppError(Exception):
    """A rejected operation. `code` is a stable machine-readable identifier."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        conflicts: list[dict] | None = None,
        hint: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.conflicts = conflicts
        self.hint = hint
        self.details = details

    @property
    def http_status(self) -> int:
        return STATUS.get(self.code, 400)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field:
            out["field"] = self.field
        if self.conflicts:
            out["conflicts"] = self.conflicts
        if self.hint:
            out["hint"] = self.hint
        if self.details:
            out["details"] = self.details
        return out


def validation(message: str, field: str | None = None, hint: str | None = None) -> AppError:
    return AppError("VALIDATION", message, field=field, hint=hint)


def not_found(entity: str, ident: Any) -> AppError:
    return AppError("NOT_FOUND", f"{entity} {ident} not found")
