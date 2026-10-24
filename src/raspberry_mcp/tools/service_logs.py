"""Bounded log retrieval for application containers."""

from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from raspberry_mcp.tools._docker import ServiceName, run_docker
from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


MAX_LOG_CHARACTERS = 65536


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_service_logs(
        service_name: ServiceName,
        lines: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> dict[str, Any]:
        """Read the last 1–1000 log lines with timestamps from a Docker container.

        Includes stdout and stderr, also for stopped containers. Output is capped
        at 65536 characters; truncated output keeps the most recent characters.
        Logs may contain application secrets or personal data.
        """
        output = run_docker(
            ["container", "logs", "--timestamps", "--tail", str(lines), service_name],
            merge_logs=True,
        )
        truncated = len(output) > MAX_LOG_CHARACTERS
        log_lines = output[-MAX_LOG_CHARACTERS:].splitlines()
        # Docker may tail stdout and stderr separately depending on its log driver.
        truncated = truncated or len(log_lines) > lines
        log_lines = log_lines[-lines:]
        return {
            "service_name": service_name,
            "lines_requested": lines,
            "lines_returned": len(log_lines),
            "truncated": truncated,
            "log_lines": log_lines,
        }
