"""Minimal single-user OAuth 2.1 authorization server so Claude can connect to /mcp as a custom connector.

Stateless on purpose: client ids and authorization codes are signed, short-lived JWTs. The access token it
issues is the same non-expiring JWT used by the web app (revocable through `token_version`).
"""

from __future__ import annotations

import base64
import hashlib
import html
import time
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core import db as dbmod, ratelimit
from app.core.config import get_settings
from app.core.security import create_short_token, create_token, decode_short_token, decode_token
from app.domains.identity import service as identity
from app.domains.identity.models import User
from app.mcp.auth import base_url

router = APIRouter()
_used_codes: dict[str, float] = {}


def _err(error: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": error, "error_description": description}, status_code=status)


# ---------------------------------------------------------------- discovery
@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource(request: Request):
    b = base_url(request)
    return {"resource": f"{b}/mcp", "authorization_servers": [b], "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp"]}


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
def auth_server_metadata(request: Request):
    b = base_url(request)
    return {
        "issuer": b,
        "authorization_endpoint": f"{b}/oauth/authorize",
        "token_endpoint": f"{b}/oauth/token",
        "registration_endpoint": f"{b}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


# ---------------------------------------------------------------- dynamic client registration
def _redirect_ok(uri: str) -> bool:
    p = urlparse(uri)
    host = (p.hostname or "").lower()
    allowed = get_settings().redirect_hosts
    if p.scheme == "https":
        return any(host == h or host.endswith("." + h) for h in allowed)
    if p.scheme == "http":
        return host in ("localhost", "127.0.0.1", "[::1]", "::1")
    return False


@router.post("/oauth/register")
async def register(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return _err("invalid_client_metadata", "JSON body required")
    uris = body.get("redirect_uris") or []
    if not uris or not all(isinstance(u, str) and _redirect_ok(u) for u in uris):
        return _err("invalid_redirect_uri", "redirect_uris must be https URLs on an allowed host (see OAUTH_ALLOWED_REDIRECT_HOSTS)")
    name = str(body.get("client_name") or "MCP client")[:80]
    client_id = create_short_token("client", 60 * 60 * 24 * 365 * 10, uris=uris, name=name)
    return JSONResponse(
        {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": name,
            "redirect_uris": uris,
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
        status_code=201,
    )


# ---------------------------------------------------------------- authorize
_PAGE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Autorizar acesso · Personal OS</title>
<style>
:root{{color-scheme:light dark;--bg:#faf9f7;--fg:#161514;--mut:#77726a;--card:#fff;--line:#e8e5df;--acc:#1f1d1a}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f0f10;--fg:#f3f1ed;--mut:#9b968c;--card:#19191b;--line:#2b2b2e;--acc:#f3f1ed}}}}
body{{margin:0;min-height:100dvh;display:grid;place-items:center;background:var(--bg);color:var(--fg);
font:16px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}}
main{{width:min(420px,calc(100vw - 32px));background:var(--card);border:1px solid var(--line);border-radius:20px;padding:28px}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:var(--mut);margin:0 0 20px;font-size:14px}}
label{{display:block;font-size:13px;color:var(--mut);margin:12px 0 4px}}
input{{width:100%;box-sizing:border-box;padding:12px 14px;border-radius:12px;border:1px solid var(--line);
background:transparent;color:var(--fg);font:inherit}}
button{{margin-top:20px;width:100%;padding:13px;border:0;border-radius:12px;background:var(--acc);color:var(--bg);
font:inherit;font-weight:600;cursor:pointer}}
.err{{color:#c2410c;font-size:14px;margin-top:12px}} small{{display:block;margin-top:14px;color:var(--mut);font-size:12px}}
</style></head><body><main>
<h1>Conectar {client} ao Personal OS</h1>
<p>Entre com sua conta para permitir que o <b>{client}</b> leia e altere sua agenda, tarefas, projetos, estudos e treinos.</p>
<form method="post" action="/oauth/authorize">{hidden}
<label>E-mail</label><input name="email" type="email" autocomplete="username" required autofocus>
<label>Senha</label><input name="password" type="password" autocomplete="current-password" required>
{error}<button type="submit">Autorizar acesso</button>
<small>Redireciona para {host}. O acesso só termina se você revogar em Configurações.</small></form></main></body></html>"""

_FIELDS = ("client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method", "scope", "response_type")


def _render(fields: dict[str, str], client_name: str, error: str = "", status: int = 200) -> HTMLResponse:
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(fields.get(k, ""), quote=True)}">' for k in _FIELDS
    )
    host = urlparse(fields.get("redirect_uri", "")).hostname or ""
    page = _PAGE.format(
        client=html.escape(client_name), hidden=hidden, host=html.escape(host),
        error=f'<div class="err">{html.escape(error)}</div>' if error else "",
    )
    return HTMLResponse(page, status_code=status)


def _validate_request(fields: dict[str, str]) -> tuple[dict | None, str | None]:
    client = decode_short_token(fields.get("client_id", ""), "client")
    if not client:
        return None, "client_id inválido"
    if fields.get("redirect_uri") not in client["uris"]:
        return None, "redirect_uri não registrada para este cliente"
    if fields.get("response_type") != "code":
        return None, "response_type deve ser 'code'"
    if not fields.get("code_challenge") or fields.get("code_challenge_method") != "S256":
        return None, "PKCE (S256) é obrigatório"
    return client, None


@router.get("/oauth/authorize")
def authorize_form(request: Request):
    fields = {k: request.query_params.get(k, "") for k in _FIELDS}
    client, err = _validate_request(fields)
    if err:
        return HTMLResponse(f"<h3>Pedido de autorização inválido</h3><p>{html.escape(err)}</p>", status_code=400)
    return _render(fields, client["name"])


@router.post("/oauth/authorize")
async def authorize_submit(
    request: Request, email: str = Form(...), password: str = Form(...),
):
    form = await request.form()
    fields = {k: str(form.get(k, "")) for k in _FIELDS}
    client, err = _validate_request(fields)
    if err:
        return HTMLResponse(f"<h3>Pedido de autorização inválido</h3><p>{html.escape(err)}</p>", status_code=400)
    ip = request.client.host if request.client else "?"
    if ratelimit.blocked(ip):
        return _render(fields, client["name"], "Muitas tentativas. Aguarde alguns minutos.", 429)
    with dbmod.SessionLocal() as db:
        user = identity.authenticate(db, email, password)
        if user is None:
            ratelimit.record_failure(ip)
            return _render(fields, client["name"], "E-mail ou senha inválidos.", 401)
        code = create_short_token(
            "code", 300, sub=str(user.id), tv=user.token_version, cid=fields["client_id"],
            ru=fields["redirect_uri"], cc=fields["code_challenge"], jti=base64.urlsafe_b64encode(
                hashlib.sha256(f"{time.time_ns()}{user.id}".encode()).digest()
            ).decode()[:22],
        )
    q = {"code": code}
    if fields.get("state"):
        q["state"] = fields["state"]
    sep = "&" if "?" in fields["redirect_uri"] else "?"
    return RedirectResponse(fields["redirect_uri"] + sep + urlencode(q), status_code=302)


# ---------------------------------------------------------------- token
def _issue(user: User) -> dict:
    return {
        "access_token": create_token(user.id, user.token_version, "access"),
        "token_type": "Bearer",
        "refresh_token": create_token(user.id, user.token_version, "refresh"),
        "scope": "mcp",
    }


@router.post("/oauth/token")
async def token(request: Request):
    form = await request.form()
    grant = form.get("grant_type")
    if grant == "authorization_code":
        claims = decode_short_token(str(form.get("code", "")), "code")
        if not claims:
            return _err("invalid_grant", "Authorization code is invalid or expired")
        now = time.time()
        for k in [k for k, v in _used_codes.items() if v < now]:
            _used_codes.pop(k, None)
        if claims["jti"] in _used_codes:
            return _err("invalid_grant", "Authorization code already used")
        verifier = str(form.get("code_verifier", ""))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        if not verifier or challenge != claims["cc"]:
            return _err("invalid_grant", "PKCE verification failed")
        if form.get("redirect_uri") and form.get("redirect_uri") != claims["ru"]:
            return _err("invalid_grant", "redirect_uri mismatch")
        if form.get("client_id") and form.get("client_id") != claims["cid"]:
            return _err("invalid_client", "client_id mismatch")
        _used_codes[claims["jti"]] = now + 600
        user_id, tv = int(claims["sub"]), claims["tv"]
    elif grant == "refresh_token":
        claims = decode_token(str(form.get("refresh_token", "")), expected_typ="refresh")
        if not claims:
            return _err("invalid_grant", "Refresh token is invalid or revoked")
        user_id, tv = int(claims["sub"]), claims["tv"]
    else:
        return _err("unsupported_grant_type", "Use authorization_code or refresh_token")
    with dbmod.SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or user.token_version != tv:
            return _err("invalid_grant", "Access was revoked")
        return JSONResponse(_issue(user), headers={"Cache-Control": "no-store"})
