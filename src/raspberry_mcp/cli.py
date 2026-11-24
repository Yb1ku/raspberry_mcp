"""Command-line entry point for the Raspberry MCP server."""

import os

import uvicorn

from raspberry_mcp.auth import TOKEN_ENV_VAR, validate_token
from raspberry_mcp.server import create_app
from raspberry_mcp.host import configure_host_metrics


def main() -> None:
    try:
        token = validate_token(os.environ.get(TOKEN_ENV_VAR))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    host = os.environ.get("RASPBERRY_MCP_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("RASPBERRY_MCP_PORT", "8000"))
    except ValueError as exc:
        raise SystemExit("RASPBERRY_MCP_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("RASPBERRY_MCP_PORT must be between 1 and 65535.")

    configure_host_metrics()
    uvicorn.run(create_app(token, host), host=host, port=port, log_level="info")
