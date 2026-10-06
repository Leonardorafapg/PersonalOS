import json

from tests.conftest import mcp_call


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"email": "owner@test.dev", "password": "nope"})
    assert r.status_code == 401


def test_token_never_expires_and_cookie_auth(client):
    import jwt

    claims = jwt.decode(client.token, options={"verify_signature": False})
    assert "exp" not in claims
    r = client.get("/auth/me")  # cookie set by login
    assert r.status_code == 200 and r.json()["data"]["email"] == "owner@test.dev"
    assert r.json()["data"]["mcp_url"].endswith("/mcp")


def test_rest_requires_auth(client):
    client.cookies.clear()
    assert client.get("/tasks").status_code == 401


def test_revoke_all_invalidates_old_tokens(client):
    old = client.token
    r = client.post("/auth/revoke-all")
    assert r.status_code == 200
    r2 = client.get("/tasks", headers={"Authorization": f"Bearer {old}"}, cookies={})
    client.cookies.clear()
    r2 = client.get("/tasks", headers={"Authorization": f"Bearer {old}"})
    assert r2.status_code == 401
    r3 = client.get("/tasks", headers={"Authorization": f"Bearer {r.json()['data']['token']}"})
    assert r3.status_code == 200


def test_mcp_requires_token_and_advertises_metadata(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401
    assert "resource_metadata" in r.headers["www-authenticate"]
    meta = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert meta["resource"].endswith("/mcp")
    asm = client.get("/.well-known/oauth-authorization-server").json()
    assert asm["code_challenge_methods_supported"] == ["S256"]


def test_mcp_lists_tools(client):
    headers = {"Authorization": f"Bearer {client.token}", "Accept": "application/json, text/event-stream"}
    r = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"get_context", "get_schedule", "list_tasks", "get_projects", "get_study", "get_operation_log",
            "save_tasks", "save_calendar_entries", "set_day_plan", "save_projects", "save_study_topics",
            "log_study", "save_routines", "save_preferences", "delete_entity", "undo_operation"} <= names
    assert len(names) == 18


def test_mcp_get_context_and_actor_is_claude(client):
    env = mcp_call(client, "get_context", expect_ok=True)
    d = env["data"]
    assert d["today"] == "2026-10-07" and d["weekday"] == "quarta"
    assert d["timezone"] == "America/Sao_Paulo"
    env = mcp_call(client, "save_tasks", {"items": [{"title": "Revisar orchestrator"}]}, expect_ok=True)
    assert env["data"]["results"][0]["task"]["created_by"] == "claude"
    assert env["meta"]["batch_id"].startswith("op_")
    log = mcp_call(client, "get_operation_log", {}, expect_ok=True)["data"]["batches"]
    assert log[0]["actor"] == "claude" and log[0]["channel"] == "mcp" and log[0]["tool"] == "save_tasks"


def test_mcp_error_is_iserror_with_code(client):
    headers = {"Authorization": f"Bearer {client.token}", "Accept": "application/json, text/event-stream"}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "save_tasks", "arguments": {"items": [{"id": "t999", "version": 1, "title": "x"}]}}}
    r = client.post("/mcp", headers=headers, json=body).json()["result"]
    assert r["isError"] is True
    env = json.loads(r["content"][0]["text"])
    assert env["error"]["code"] == "NOT_FOUND"


def test_oauth_flow_end_to_end(client):
    import base64
    import hashlib
    from urllib.parse import parse_qs, urlparse

    reg = client.post("/oauth/register", json={"client_name": "Claude", "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]})
    assert reg.status_code == 201
    cid = reg.json()["client_id"]
    bad = client.post("/oauth/register", json={"redirect_uris": ["https://evil.example.com/cb"]})
    assert bad.status_code == 400
    verifier = "v" * 50
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"response_type": "code", "client_id": cid, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
              "state": "xyz", "code_challenge": challenge, "code_challenge_method": "S256", "scope": "mcp"}
    page = client.get("/oauth/authorize", params=params)
    assert page.status_code == 200 and "Autorizar" in page.text
    wrong = client.post("/oauth/authorize", data={**params, "email": "owner@test.dev", "password": "bad"})
    assert wrong.status_code == 401
    ok = client.post("/oauth/authorize", data={**params, "email": "owner@test.dev", "password": "supersecret1"},
                     follow_redirects=False)
    assert ok.status_code == 302
    loc = urlparse(ok.headers["location"])
    q = parse_qs(loc.query)
    assert q["state"] == ["xyz"]
    code = q["code"][0]
    tok = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code,
                                            "code_verifier": verifier, "client_id": cid,
                                            "redirect_uri": params["redirect_uri"]})
    assert tok.status_code == 200, tok.text
    access = tok.json()["access_token"]
    again = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code,
                                              "code_verifier": verifier, "client_id": cid})
    assert again.status_code == 400  # single use
    env = mcp_call(client, "get_context", token=access, expect_ok=True)
    assert env["data"]["today"] == "2026-10-07"
    refreshed = client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok.json()["refresh_token"]})
    assert refreshed.status_code == 200


def test_login_is_rate_limited(client):
    for _ in range(10):
        assert client.post("/auth/login", json={"email": "owner@test.dev", "password": "wrong"}).status_code == 401
    r = client.post("/auth/login", json={"email": "owner@test.dev", "password": "supersecret1"})
    assert r.status_code == 429
