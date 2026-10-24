"""MCP health check tool."""

from mcp.server import MCPServer

from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def health_check() -> str:
        """Check that the MCP server can handle an authenticated tool call."""
        return "ok"
