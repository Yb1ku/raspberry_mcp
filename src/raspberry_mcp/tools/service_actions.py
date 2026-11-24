"""Controlled lifecycle actions for application containers."""

import os
import threading
from datetime import datetime, timezone
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from raspberry_mcp.tools._docker import ServiceName, inspect_service, run_docker


ENABLED_ACTIONS_ENV_VAR = "RASPBERRY_MCP_ENABLED_ACTIONS"
ALLOWED_SERVICES_ENV_VAR = "RASPBERRY_MCP_ALLOWED_SERVICES"
SUPPORTED_ACTIONS = ("start", "stop", "restart")
_DOCKER_ACTION_COMMANDS = {
    "start": ["container", "start"],
    "stop": ["container", "stop"],
    "restart": ["container", "restart"],
}

START_STOP_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

RESTART_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)

_SERVICE_LOCKS: dict[str, threading.Lock] = {}
_SERVICE_LOCKS_GUARD = threading.Lock()


def _configured_values(name: str) -> set[str]:
    """Return configured values; missing or blank configuration denies access."""
    raw = os.environ.get(name, "")
    return {value.strip() for value in raw.split(",") if value.strip()}


def enabled_actions() -> list[str]:
    """Return lifecycle actions enabled by configuration."""
    configured = _configured_values(ENABLED_ACTIONS_ENV_VAR)
    unknown = configured - set(SUPPORTED_ACTIONS)
    if unknown:
        raise ValueError(
            f"{ENABLED_ACTIONS_ENV_VAR} contains unsupported actions: "
            f"{', '.join(sorted(unknown))}."
        )
    return [action for action in SUPPORTED_ACTIONS if action in configured]


def _check_authorized(service_name: str, action: str) -> None:
    allowed_services = _configured_values(ALLOWED_SERVICES_ENV_VAR)
    if service_name not in allowed_services:
        raise ValueError(f"Service {service_name!r} is not allowed for lifecycle actions.")
    if action not in enabled_actions():
        raise ValueError(f"Action {action!r} is not enabled for this MCP server.")


def allowed_actions_for_service(service_name: str) -> list[str]:
    """Return enabled lifecycle actions for a specific service."""
    allowed_services = _configured_values(ALLOWED_SERVICES_ENV_VAR)
    if service_name not in allowed_services:
        return []
    return enabled_actions()


def _service_lock(service_name: str) -> threading.Lock:
    """Get the process-local lifecycle lock for one service."""
    with _SERVICE_LOCKS_GUARD:
        return _SERVICE_LOCKS.setdefault(service_name, threading.Lock())


def _action_result(
    service_name: str,
    action: str,
    previous_status: str,
    changed: bool,
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect after an action and return a stable, useful result."""
    current = current or inspect_service(service_name)
    return {
        "service_name": service_name,
        "action": action,
        "changed": changed,
        "previous_status": previous_status,
        "status": current["status"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def _run_lifecycle_action(service_name: str, action: str) -> dict[str, Any]:
    _check_authorized(service_name, action)
    with _service_lock(service_name):
        previous = inspect_service(service_name)
        previous_status = previous["status"]

        if action == "start" and previous_status == "running":
            return _action_result(
                service_name, action, previous_status, changed=False, current=previous
            )
        if action == "stop" and previous_status != "running":
            return _action_result(
                service_name, action, previous_status, changed=False, current=previous
            )

        # Keep the Docker command fixed; policy validation must never become
        # shell-like command construction if this function is reused later.
        run_docker([*_DOCKER_ACTION_COMMANDS[action], service_name])
        current = inspect_service(service_name)
        current_status = current["status"]
        expected_running = action in {"start", "restart"}
        if (current_status == "running") != expected_running:
            expected = "running" if expected_running else "stopped"
            raise ValueError(
                f"Service {service_name!r} did not reach the expected state "
                f"{expected!r}; current state is {current_status!r}."
            )
        return _action_result(
            service_name, action, previous_status, changed=True, current=current
        )


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=START_STOP_ANNOTATIONS)
    def start_service(service_name: ServiceName) -> dict[str, Any]:
        """Start a Docker service if it is not already running."""
        return _run_lifecycle_action(service_name, "start")

    @server.tool(annotations=START_STOP_ANNOTATIONS)
    def stop_service(service_name: ServiceName) -> dict[str, Any]:
        """Stop a Docker service if it is currently running."""
        return _run_lifecycle_action(service_name, "stop")

    @server.tool(annotations=RESTART_ANNOTATIONS)
    def restart_service(service_name: ServiceName) -> dict[str, Any]:
        """Restart a Docker service."""
        return _run_lifecycle_action(service_name, "restart")
