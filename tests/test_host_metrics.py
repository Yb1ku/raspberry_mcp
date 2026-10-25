"""Container deployments must continue reporting the Pi's disks and metrics."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from raspberry_mcp.host import configure_host_metrics, mounted_device
from raspberry_mcp.tools import storage


class HostMetricsTests(unittest.TestCase):
    def test_procfs_uses_host_mount(self):
        with (
            patch.dict(os.environ, {"RASPBERRY_MCP_HOST_ROOT": "/host"}),
            patch("raspberry_mcp.host.psutil.PROCFS_PATH", "/proc"),
        ):
            configure_host_metrics()
            self.assertEqual(storage.psutil.PROCFS_PATH, "/host/proc")

    def test_host_mount_table_decodes_spaces(self):
        with tempfile.TemporaryDirectory() as root:
            table = Path(root) / "proc/1/mounts"
            table.parent.mkdir(parents=True)
            table.write_text("/dev/sda1 /mnt/my\\040disk ext4 rw 0 0\n")
            with patch.dict(os.environ, {"RASPBERRY_MCP_HOST_ROOT": root}):
                self.assertEqual(
                    mounted_device(Path("/mnt/my disk")), ("/dev/sda1", "ext4")
                )
                self.assertIsNone(mounted_device(Path("/mnt/missing")))

    def test_host_disk_identity_and_usage_are_not_container_overlay(self):
        with (
            patch.dict(os.environ, {"RASPBERRY_MCP_HOST_ROOT": "/host"}),
            patch.object(
                storage, "mounted_device", return_value=("/dev/mmcblk0p2", "ext4")
            ),
            patch.object(storage.psutil, "disk_usage") as usage,
        ):
            usage.return_value.total = 100
            usage.return_value.used = 60
            usage.return_value.free = 40
            usage.return_value.percent = 60
            result = storage._volume_info("internal", "/")
            usage.assert_called_once_with("/host")
            self.assertEqual(result["device"], "/dev/mmcblk0p2")
            self.assertEqual(result["mountpoint"], "/")
            self.assertEqual(result["device_type"], "flash")

    def test_missing_host_disk_is_unavailable(self):
        with (
            patch.dict(os.environ, {"RASPBERRY_MCP_HOST_ROOT": "/host"}),
            patch.object(storage, "mounted_device", return_value=None),
            patch.object(storage.psutil, "disk_usage") as usage,
        ):
            result = storage._volume_info("external", "/mnt/media")
            self.assertFalse(result["available"])
            usage.assert_not_called()
