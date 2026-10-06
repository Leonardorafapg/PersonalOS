import os
import tempfile
from datetime import datetime, timezone

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ADMIN_EMAIL"] = "owner@test.dev"
os.environ["ADMIN_PASSWORD"] = "supersecret1"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["ENVIRONMENT"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.core import clock, db as dbmod  # noqa: E402
from app.core.db import Base  # noqa: E402

# Wednesday 2026-10-07 08:00 in America/Sao_Paulo (UTC-3)
NOW = datetime(2026, 10, 7, 11, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client():
    from app.core import ratelimit

    ratelimit._fails.clear()
    Base.metadata.drop_all(dbmod.engine)
    Base.metadata.create_all(dbmod.engine)
    clock.freeze(NOW)
    from app.main import create_app

    with TestClient(create_app()) as c:
        r = c.post("/auth/login", json={"email": "owner@test.dev", "password": "supersecret1"})
        assert r.status_code == 200, r.text
        c.token = r.json()["data"]["token"]
        yield c
    clock.freeze(None)


@pytest.fixture()
def user_id(client):
    return 1


def mcp_call(client, tool, args=None, *, token=None, expect_ok=None):
    """Call an MCP tool through the real HTTP endpoint (stateless streamable HTTP, JSON responses)."""
    import json

    headers = {
        "Authorization": f"Bearer {token or client.token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args or {}}}
    r = client.post("/mcp", headers=headers, content=json.dumps(body))
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    text = result["content"][0]["text"]
    try:
        env = json.loads(text)
    except ValueError:  # argument-schema validation errors are produced by the MCP framework as plain text
        assert result["isError"] is True
        env = {"ok": False, "error": {"code": "VALIDATION", "message": text}}
    if expect_ok is not None:
        assert env["ok"] is expect_ok, env
    return env
