import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ToolFailure(RuntimeError):
    pass


class ProcurementTools:
    def __init__(self, session, schemas):
        self.session, self.schemas = session, schemas
        self.events = []

    async def call(self, name, arguments=None):
        if name not in self.schemas:
            raise ToolFailure(f"Tool not discovered: {name}")
        for attempt in range(1, 4):
            result = await self.session.call_tool(
                name, arguments or {}, read_timeout_seconds=timedelta(seconds=20)
            )
            content = result.structuredContent
            if content is None:
                raw = "\n".join(x.text for x in result.content if x.type == "text")
                try:
                    content = json.loads(raw)
                except json.JSONDecodeError:
                    content = {"error": raw}
            if isinstance(content, dict) and set(content) == {"result"}:
                content = content["result"]
            retryable = isinstance(content, dict) and content.get("retryable", False)
            ok = not result.isError and not (
                isinstance(content, dict) and "error" in content
            )
            self.events.append(
                {
                    "tool": name,
                    "attempt": attempt,
                    "ok": ok,
                    "detail": content.get("error", "Completed")
                    if isinstance(content, dict)
                    else "Completed",
                }
            )
            if ok:
                return content
            if not retryable or attempt == 3:
                raise ToolFailure(str(content))
            await asyncio.sleep(0.15 * attempt)
        raise ToolFailure("Tool retry budget exhausted")


@asynccontextmanager
async def connect_tools(home):
    env = dict(os.environ, PROCUREFLOW_HOME=str(home))
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "procureflow.mcp_server"], env=env
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            discovered = await session.list_tools()
            schemas = {
                t.name: {"description": t.description, "inputSchema": t.inputSchema}
                for t in discovered.tools
            }
            yield ProcurementTools(session, schemas)
