"""Connects with the official MCP Python client (like any real MCP host) and exercises the server.

    python scripts/mcp_smoke.py http://localhost:8000 you@email.com yourpassword
"""
import asyncio
import json
import sys

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

base, email, password = sys.argv[1:4]
token = httpx.post(f"{base}/auth/login", json={"email": email, "password": password}).json()["data"]["token"]


async def main():
    async with streamablehttp_client(f"{base}/mcp", headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("server:", init.serverInfo.name, "| instructions:", len(init.instructions or ""), "chars")
            tools = (await s.list_tools()).tools
            print(len(tools), "tools:", ", ".join(t.name for t in tools))
            ro = [t.name for t in tools if t.annotations and t.annotations.readOnlyHint]
            print("read-only:", ro)
            res = await s.call_tool("get_context", {})
            env = json.loads(res.content[0].text)
            print("get_context ok:", env["ok"], "| today:", env["data"]["today"], "| open tasks:", env["data"]["tasks"]["open"])
            res = await s.call_tool("get_study", {"only_available": True, "limit": 3})
            print("available topics:", [a["path"].split(" › ")[-1] for a in json.loads(res.content[0].text)["data"]["available"]])


asyncio.run(main())
