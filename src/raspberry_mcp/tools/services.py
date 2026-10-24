"""Discover Docker application services and their available actions."""

import json
from datetime import datetime, timezone
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel, Field

from raspberry_mcp.tools._docker import run_docker
from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


_DISCOVERY_FORMAT = (
    '{"id":{{json .Id}},"name":{{json .Name}},'
    '"image":{{json .Config.Image}},"status":{{json .State.Status}},'
    '"health":{{with index .State "Health"}}{{json .Status}}{{else}}null{{end}},'
    '"started_at":{{json .State.StartedAt}},'
    '"network_mode":{{json .HostConfig.NetworkMode}},'
    '"ports":{{json .NetworkSettings.Ports}}}'
)


class DiscoveredService(BaseModel):
    """A container's current state and capabilities exposed by this MCP."""

    id: str
    name: str
    image: str
    status: str
    health: str | None
    started_at: str | None
    time_active_seconds: int | None = Field(
        description="Elapsed seconds since the current start; null unless running."
    )
    allowed_actions: list[str] = Field(
        description="Actions implemented and authorized by this MCP for this container."
    )
    network_mode: str
    ports: dict[str, list[dict[str, str]] | None]


def _service_info(container: dict[str, Any], now: datetime) -> DiscoveredService:
    raw_started_at = container.get("started_at")
    started_at = None
    elapsed = None
    if raw_started_at:
        try:
            start = datetime.fromisoformat(raw_started_at.replace("Z", "+00:00"))
            if start.tzinfo is None:
                raise ValueError("Start time has no timezone")
            # Docker uses the year-one timestamp for containers never started.
            if start.year != 1:
                started_at = raw_started_at
                if container["status"] == "running":
                    elapsed = max(0, int((now - start).total_seconds()))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Docker returned an invalid container start time.") from exc

    return DiscoveredService(
        id=container["id"],
        name=container["name"].removeprefix("/"),
        image=container["image"],
        status=container["status"],
        health=container.get("health"),
        started_at=started_at,
        time_active_seconds=elapsed,
        # No control tools are implemented yet. Never advertise unsupported actions.
        allowed_actions=[],
        network_mode=container["network_mode"],
        ports=container.get("ports") or {},
    )


def _discover_services() -> list[DiscoveredService]:
    ids = run_docker(["container", "ls", "--all", "--no-trunc", "--format", "{{.ID}}"])
    container_ids = ids.split()
    if not container_ids:
        return []

    output = run_docker([
        "container", "inspect", "--format", _DISCOVERY_FORMAT, *container_ids,
    ])
    now = datetime.now(timezone.utc)
    services = []
    try:
        for line in output.splitlines():
            container = json.loads(line)
            services.append(_service_info(container, now))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Docker returned invalid service discovery data.") from exc
    return sorted(services, key=lambda service: service.name)


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def discover_services() -> list[DiscoveredService]:
        """Discover all Docker services, including stopped containers.

        Returns exact names to pass to service tools, state, optional healthcheck,
        last start timestamp and elapsed seconds since the current start.
        Elapsed time includes any pauses since that start and is null unless
        running. Actions are empty until control tools and authorization exist.
        Docker access failures are tool errors, not an empty discovery result.
        """
        return _discover_services()
