"""Authenticated MCP readiness probe, also used by Docker HEALTHCHECK."""

import asyncio
import os

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def check() -> None:
    port = int(os.environ.get("RASPBERRY_MCP_PORT", "8000"))
    token = os.environ["RASPBERRY_MCP_TOKEN"]
    async with asyncio.timeout(10):
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}
        ) as client:
            async with streamable_http_client(
                f"http://127.0.0.1:{port}/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool("health_check")
                    if result.is_error or not any(
                        getattr(item, "text", None) == "ok" for item in result.content
                    ):
                        raise RuntimeError("MCP health_check did not return ok")


if __name__ == "__main__":
    # Do not emit exception details that might contain credentials or HTTP headers.
    try:
        asyncio.run(check())
    except Exception:
        raise SystemExit("MCP readiness probe failed") from None
