"""MCP health check tool."""

import os

from mcp.server import MCPServer

from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def health_check() -> str:
        """Check that the MCP server can handle an authenticated tool call."""
        return "ok"

    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_server_version() -> dict[str, str]:
        """Identify the deployed source commit and environment."""
        return {
            "revision": os.environ.get("RASPBERRY_MCP_REVISION", "unknown"),
            "environment": os.environ.get("RASPBERRY_MCP_ENVIRONMENT", "local"),
        }
