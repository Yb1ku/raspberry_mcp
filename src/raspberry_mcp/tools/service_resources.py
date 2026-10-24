"""Resource usage snapshots for application containers."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from mcp.server import MCPServer

from raspberry_mcp.tools._docker import ServiceName, inspect_service, run_docker
from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


def _bytes(value: str) -> int:
    """Convert Docker's decimal or binary display units into approximate bytes."""
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMgGtTpPeE]?i?[bB])\s*", value)
    if not match:
        raise ValueError(f"Unrecognized Docker size: {value!r}")
    number, unit = match.groups()
    unit = unit.lower()
    exponent = "bkmgtpe".index(unit[0]) if unit != "b" else 0
    return int(Decimal(number) * (1024 if "i" in unit else 1000) ** exponent)


def _pair(value: str) -> tuple[int, int]:
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError("Docker returned invalid resource counters.")
    return _bytes(parts[0]), _bytes(parts[1])


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_service_resources(service_name: ServiceName) -> dict[str, Any]:
        """Get a running Docker container's CPU, RAM, network and disk counters.

        CPU percent can exceed 100 when multiple cores are busy. Network and disk
        bytes are cumulative counters, not transfer rates. Values are approximate
        because Docker CLI display units are rounded. Host-network containers
        have null network counters because Docker does not isolate that traffic.
        """
        state = inspect_service(service_name)
        if state["status"] != "running":
            raise ValueError(f"Service {service_name!r} is {state['status']}; resource stats require a running container.")

        output = run_docker([
            "container", "stats", "--no-stream", "--format", "{{json .}}", service_name,
        ])
        if not output.strip():
            raise ValueError("No resource statistics returned; the container may have stopped.")
        try:
            stats = json.loads(output)
            used, limit = _pair(stats["MemUsage"])
            received, sent = _pair(stats["NetIO"])
            read, written = _pair(stats["BlockIO"])
            cpu_percent = float(stats["CPUPerc"].rstrip("%"))
            memory_percent = float(stats["MemPerc"].rstrip("%"))
            pids = int(stats["PIDs"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("Docker returned invalid resource statistics.") from exc

        network_available = state["network_mode"] != "host"
        return {
            "service_name": service_name,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "cpu_percent": cpu_percent,
            "memory": {"used_bytes": used, "limit_bytes": limit, "used_percent": memory_percent},
            "network": {
                "available": network_available,
                "mode": state["network_mode"],
                "received_bytes": received if network_available else None,
                "sent_bytes": sent if network_available else None,
            },
            "disk_io": {"read_bytes": read, "written_bytes": written},
            "processes_and_threads": pids,
        }
