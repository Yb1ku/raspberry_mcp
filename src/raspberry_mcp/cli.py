"""Command-line entry point for the Raspberry MCP server."""

import os

import uvicorn

from raspberry_mcp.server import create_app
from raspberry_mcp.host import configure_host_metrics


TOKEN_ENV_VAR = "RASPBERRY_MCP_TOKEN"


def main() -> None:
    token = os.environ.get(TOKEN_ENV_VAR, "")
    if not token.strip():
        raise SystemExit(
            f"Missing required environment variable {TOKEN_ENV_VAR}. "
            "Set it to a long, random secret before starting the server."
        )

    host = os.environ.get("RASPBERRY_MCP_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("RASPBERRY_MCP_PORT", "8000"))
    except ValueError as exc:
        raise SystemExit("RASPBERRY_MCP_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("RASPBERRY_MCP_PORT must be between 1 and 65535.")

    configure_host_metrics()
    uvicorn.run(create_app(token, host), host=host, port=port, log_level="info")
