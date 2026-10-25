"""Read host information when the Pi root is mounted inside a container."""

import os
from pathlib import Path

import psutil


def host_path(path: str) -> Path:
    root = os.environ.get("RASPBERRY_MCP_HOST_ROOT", "")
    return Path(root) / path.lstrip("/") if root else Path(path)


def configure_host_metrics() -> None:
    if os.environ.get("RASPBERRY_MCP_HOST_ROOT"):
        psutil.PROCFS_PATH = str(host_path("/proc"))


def mounted_device(path: Path) -> tuple[str, str] | None:
    """Look up an exact mountpoint in the host init process's mount table."""
    for line in host_path("/proc/1/mounts").read_text().splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        device, mountpoint, filesystem = fields[:3]
        mountpoint = (
            mountpoint.replace(r"\040", " ")
            .replace(r"\011", "\t")
            .replace(r"\134", "\\")
        )
        if Path(mountpoint) == path:
            return device, filesystem
    return None
