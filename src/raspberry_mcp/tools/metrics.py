"""CPU, memory, temperature, and uptime tools."""

import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

import psutil
from mcp.server import MCPServer

from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS
from raspberry_mcp.host import host_path


def _read_cpu_temperature() -> dict[str, Any]:
    """Read a Linux thermal zone, then fall back to psutil or vcgencmd."""
    zones = sorted(host_path("/sys/class/thermal").glob("thermal_zone*"))
    readings: list[tuple[str, float]] = []
    for zone in zones:
        try:
            label = (zone / "type").read_text().strip()
            value = float((zone / "temp").read_text().strip()) / 1000.0
            readings.append((label, value))
        except (OSError, ValueError):
            continue

    if readings:
        selected = next(
            (item for item in readings if "cpu" in item[0].lower()),
            next((item for item in readings if "soc" in item[0].lower()), readings[0]),
        )
        return {
            "available": True,
            "temperature_celsius": round(selected[1], 1),
            "sensor": selected[0],
        }

    try:
        for sensor_group, sensors in psutil.sensors_temperatures().items():
            if sensors:
                sensor = sensors[0]
                return {
                    "available": True,
                    "temperature_celsius": round(sensor.current, 1),
                    "sensor": sensor.label or sensor_group,
                }
    except (NotImplementedError, OSError):
        pass

    try:
        output = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        ).stdout
        match = re.search(r"temp=([0-9]+(?:\.[0-9]+)?)'C", output)
        if match:
            return {
                "available": True,
                "temperature_celsius": float(match.group(1)),
                "sensor": "vcgencmd",
            }
    except (OSError, subprocess.SubprocessError):
        pass

    return {"available": False, "temperature_celsius": None, "sensor": None}


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_system_metrics() -> dict[str, Any]:
        """Get CPU temperature and usage, RAM usage, and system uptime."""
        memory = psutil.virtual_memory()
        try:
            load_1m, load_5m, load_15m = os.getloadavg()
        except (AttributeError, OSError):
            load_1m = load_5m = load_15m = None

        uptime = max(0, datetime.now(timezone.utc).timestamp() - psutil.boot_time())
        return {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "temperature": _read_cpu_temperature(),
            "cpu": {
                "usage_percent": psutil.cpu_percent(interval=0.2),
                "logical_cores": psutil.cpu_count(logical=True),
                "load_average": {
                    "1m": load_1m,
                    "5m": load_5m,
                    "15m": load_15m,
                },
            },
            "memory": {
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "used_bytes": memory.total - memory.available,
                "used_percent": memory.percent,
            },
            "uptime_seconds": int(uptime),
        }
