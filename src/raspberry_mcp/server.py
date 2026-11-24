"""MCP server and HTTP application construction."""

from mcp.server import MCPServer
from starlette.applications import Starlette

from raspberry_mcp.auth import BearerTokenMiddleware, validate_token
from raspberry_mcp.tools import register_tools


def create_server() -> MCPServer:
    """Create the MCP server and register its tools."""
    server = MCPServer("raspberry-mcp", version="0.1.0")
    register_tools(server)
    return server


def create_app(token: str, host: str) -> Starlette:
    """Build the authenticated Streamable HTTP application."""
    token = validate_token(token)
    app = create_server().streamable_http_app(host=host)
    app.add_middleware(BearerTokenMiddleware, token=token)
    return app
