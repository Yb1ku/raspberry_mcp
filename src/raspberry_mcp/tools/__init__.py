"""Tool registration for the Raspberry Pi MCP server."""

from mcp.server import MCPServer


def register_tools(server: MCPServer) -> None:
    """Register all available tools on an MCP server instance."""
    from raspberry_mcp.tools.health import register_tools as register_health_tools
    from raspberry_mcp.tools.metrics import register_tools as register_metrics_tools
    from raspberry_mcp.tools.services import register_tools as register_service_tools
    from raspberry_mcp.tools.service_status import register_tools as register_status_tools
    from raspberry_mcp.tools.service_logs import register_tools as register_log_tools
    from raspberry_mcp.tools.service_resources import register_tools as register_resource_tools
    from raspberry_mcp.tools.storage import register_tools as register_storage_tools

    register_health_tools(server)
    register_metrics_tools(server)
    register_storage_tools(server)
    register_service_tools(server)
    register_status_tools(server)
    register_log_tools(server)
    register_resource_tools(server)
