"""Starts the server over stdio with DUMMY credentials and checks the tool list.

Does not contact iCloud. Run from the repo root:  uv run python tests/smoke_test.py
"""
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = {
    "calendar_list_calendars", "calendar_list_events", "reminders_list_lists",
    "reminders_list_incomplete", "contacts_search", "calendar_create_event",
    "calendar_update_event", "calendar_delete_event", "reminders_create", "reminders_update",
    "reminders_delete",
}


async def run(env: dict) -> set:
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], env=env)
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = {t.name for t in tools.tools}
            # Missing-credentials path: must return a clear error, not crash or hit the network.
            if not env.get("APPLE_APP_PASSWORD"):
                res = await s.call_tool("calendar_list_calendars", {})
                text = " ".join(getattr(c, "text", "") for c in res.content)
                assert res.isError and "APPLE_APP_PASSWORD" in text, text
                print("missing-credentials error OK:", text[:90], "...")
            return names


base = {k: v for k, v in os.environ.items() if not k.startswith("APPLE_")}
names = asyncio.run(run({**base, "APPLE_ID": "dummy@example.com", "APPLE_APP_PASSWORD": "dummy-dummy-dummy-dummy"}))
assert names == EXPECTED, names ^ EXPECTED
print("tools OK:", sorted(names))
asyncio.run(run(base))
print("PASS")
