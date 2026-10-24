"""Detailed application container status."""

from typing import Any

from mcp.server import MCPServer

from raspberry_mcp.tools._docker import ServiceName, inspect_service
from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_service_status(service_name: ServiceName) -> dict[str, Any]:
        """Get a Docker container's state, health, restarts, exit code and OOM flag.

        Use the exact container name from discover_services. Stopped containers can
        also be queried. Health is null when no Docker healthcheck is configured.
        """
        return inspect_service(service_name)
