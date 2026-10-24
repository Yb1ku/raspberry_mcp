"""Storage usage tools."""

import os
from pathlib import Path
from typing import Any

import psutil
from mcp.server import MCPServer

from raspberry_mcp.tools.common import READ_ONLY_ANNOTATIONS


INTERNAL_STORAGE_ENV_VAR = "RASPBERRY_MCP_INTERNAL_STORAGE_PATH"
EXTERNAL_STORAGE_ENV_VAR = "RASPBERRY_MCP_EXTERNAL_STORAGE_PATH"


def _storage_type_for_device(device: str) -> str | None:
    """Report media class without mistaking flash storage for an SSD."""
    block_name = Path(device).name
    if not block_name.startswith(("sd", "vd", "xvd", "nvme", "mmcblk")):
        return None
    if block_name.startswith("mmcblk"):
        return "flash"

    block_path = (Path("/sys/class/block") / block_name).resolve()
    for candidate in (
        block_path / "queue/rotational",
        block_path.parent / "queue/rotational",
    ):
        try:
            return "hdd" if candidate.read_text().strip() == "1" else "non_rotational"
        except OSError:
            continue
    return None


def _volume_info(label: str, configured_path: str) -> dict[str, Any]:
    path = Path(configured_path).expanduser().resolve()
    partitions = psutil.disk_partitions(all=True)
    partition = next(
        (item for item in partitions if Path(item.mountpoint).resolve() == path),
        None,
    )
    if partition is None:
        return {
            "label": label,
            "available": False,
            "mountpoint": str(path),
            "error": "configured mountpoint is not mounted",
        }

    try:
        usage = psutil.disk_usage(str(path))
    except OSError as exc:
        return {
            "label": label,
            "available": False,
            "mountpoint": str(path),
            "device": partition.device,
            "error": str(exc),
        }

    return {
        "label": label,
        "available": True,
        "mountpoint": str(path),
        "device": partition.device,
        "device_type": _storage_type_for_device(partition.device),
        "filesystem": partition.fstype,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": usage.percent,
    }


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_storage_usage() -> dict[str, Any]:
        """Get usage of the configured internal and external storage mounts."""
        internal_path = os.environ.get(INTERNAL_STORAGE_ENV_VAR, "/")
        external_path = os.environ.get(EXTERNAL_STORAGE_ENV_VAR, "/mnt/media")
        return {
            "internal": _volume_info("internal", internal_path),
            "external": _volume_info("external", external_path),
        }
