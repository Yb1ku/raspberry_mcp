"""Check Docker error handling and resource unit conversion."""

import subprocess
import unittest
from unittest.mock import patch

from raspberry_mcp.tools._docker import run_docker
from raspberry_mcp.tools.service_resources import _bytes, _pair


class ResourceUnitsTests(unittest.TestCase):
    def test_decimal_and_binary_units_are_distinct(self):
        self.assertEqual(_bytes("1.5MB"), 1_500_000)
        self.assertEqual(_bytes("1.5MiB"), 1_572_864)
        self.assertEqual(_bytes("0B"), 0)
        self.assertEqual(_bytes("2.294GiB"), 2_463_163_744)

    def test_memory_pair_preserves_used_and_limit(self):
        self.assertEqual(_pair("100MiB / 1GiB"), (104_857_600, 1_073_741_824))

    def test_invalid_stats_are_not_reported_as_zero(self):
        for value in ("N/A", "", "1unknown", "-1MB"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _bytes(value)
        with self.assertRaises(ValueError):
            _pair("100MiB")


class DockerQueryTests(unittest.TestCase):
    @patch("raspberry_mcp.tools._docker.subprocess.run")
    def test_missing_service_reports_docker_error(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["docker"], 1, stdout="", stderr="Error: No such container: missing"
        )
        with self.assertRaisesRegex(ValueError, "No such container"):
            run_docker(["container", "inspect", "missing"])

    @patch("raspberry_mcp.tools._docker.subprocess.run")
    def test_timeout_is_a_clear_error(self, run):
        run.side_effect = subprocess.TimeoutExpired(["docker"], 15)
        with self.assertRaisesRegex(ValueError, "timed out"):
            run_docker(["container", "stats"])

    @patch("raspberry_mcp.tools._docker.subprocess.run")
    def test_docker_error_redacts_secret_like_values(self, run):
        run.return_value = subprocess.CompletedProcess(
            ["docker"],
            1,
            stdout="",
            stderr="failed password=super-secret token:top-secret Bearer abc123",
        )

        with self.assertRaises(ValueError) as error:
            run_docker(["container", "start", "jellyfin"])

        self.assertNotIn("super-secret", str(error.exception))
        self.assertNotIn("top-secret", str(error.exception))
        self.assertNotIn("abc123", str(error.exception))
        self.assertIn("[REDACTED]", str(error.exception))


if __name__ == "__main__":
    unittest.main()
