"""ASGI guard in front of the MCP app: Bearer token required, 401 + resource metadata pointer otherwise."""

import anyio
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.api.deps import user_from_token
from app.core.config import get_settings


def base_url(request: Request) -> str:
    s = get_settings()
    if s.public_url:
        return s.public_url.rstrip("/")
    return str(request.base_url).rstrip("/")


class McpAuth:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        if path != "/mcp" and not path.startswith("/mcp/"):
            return await Response("Not Found", status_code=404)(scope, receive, send)
        if scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        auth = Headers(scope=scope).get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        user = await anyio.to_thread.run_sync(user_from_token, token) if token else None
        if user is None:
            request = Request(scope)
            meta = f"{base_url(request)}/.well-known/oauth-protected-resource/mcp"
            resp = JSONResponse(
                {"error": "unauthorized", "error_description": "A valid access token is required"},
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer resource_metadata="{meta}"'},
            )
            return await resp(scope, receive, send)
        scope.setdefault("state", {})["user_id"] = user.id
        return await self.app(scope, receive, send)
