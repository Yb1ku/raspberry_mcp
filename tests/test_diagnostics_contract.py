"""Exercise the read-only diagnostic tools through their registered callables."""

import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from raspberry_mcp.tools import health, metrics, service_logs, service_resources
from raspberry_mcp.tools import service_status, services, storage


# This is intentionally explicit: adding a read-only tool requires adding its
# response contract here, so it cannot silently arrive without test coverage.
READ_ONLY_TOOL_CONTRACTS = {
    "health_check": {"required_keys": None},
    "get_server_version": {"required_keys": {"revision", "environment"}},
    "get_system_metrics": {
        "required_keys": {"timestamp_utc", "temperature", "cpu", "memory", "uptime_seconds"},
    },
    "get_storage_usage": {"required_keys": {"internal", "external"}},
    "discover_services": {"required_keys": None},
    "get_service_status": {
        "required_keys": {
            "service_name",
            "status",
            "health",
            "restart_count",
            "exit_code",
            "oom_killed",
            "started_at",
            "finished_at",
            "network_mode",
        },
    },
    "get_service_logs": {
        "required_keys": {
            "service_name",
            "lines_requested",
            "lines_returned",
            "truncated",
            "log_lines",
        },
    },
    "get_service_resources": {
        "required_keys": {
            "service_name",
            "timestamp_utc",
            "cpu_percent",
            "memory",
            "network",
            "disk_io",
            "processes_and_threads",
        },
    },
}


class ToolCollector:
    def __init__(self):
        self.tools = {}
        self.metadata = {}

    def tool(self, **kwargs):
        def register(function):
            self.tools[function.__name__] = function
            self.metadata[function.__name__] = kwargs
            return function

        return register


def registered_tools():
    server = ToolCollector()
    for module in (
        health,
        metrics,
        storage,
        services,
        service_status,
        service_resources,
        service_logs,
    ):
        module.register_tools(server)
    return server


@contextmanager
def mocked_system_metrics():
    memory = SimpleNamespace(total=100, available=40, percent=60)
    with (
        patch.multiple(
            metrics.psutil,
            cpu_percent=lambda interval: 12.5,
            cpu_count=lambda logical=True: 4,
            boot_time=lambda: 1_000,
            virtual_memory=lambda: memory,
        ),
        patch.object(metrics.os, "getloadavg", return_value=(1.0, 0.5, 0.25)),
        patch.object(
            metrics,
            "_read_cpu_temperature",
            return_value={
                "available": True,
                "temperature_celsius": 48.5,
                "sensor": "cpu-thermal",
            },
        ),
    ):
        yield


class DiagnosticToolTests(unittest.TestCase):
    def setUp(self):
        self.server = registered_tools()
        self.tools = self.server.tools

    def test_all_expected_read_only_tools_are_registered(self):
        self.assertEqual(set(self.tools), set(READ_ONLY_TOOL_CONTRACTS))
        for name in READ_ONLY_TOOL_CONTRACTS:
            with self.subTest(name=name):
                annotations = self.server.metadata[name]["annotations"]
                self.assertTrue(annotations.read_only_hint)
                self.assertFalse(annotations.destructive_hint)
                self.assertTrue(annotations.idempotent_hint)

    def test_contract_declares_required_response_fields(self):
        for name, contract in READ_ONLY_TOOL_CONTRACTS.items():
            with self.subTest(name=name):
                required_keys = contract["required_keys"]
                if required_keys is not None:
                    self.assertTrue(required_keys)

    def test_health_and_version_have_stable_contract(self):
        with patch.dict(
            os.environ,
            {"RASPBERRY_MCP_REVISION": "abc123", "RASPBERRY_MCP_ENVIRONMENT": "production"},
        ):
            self.assertEqual(self.tools["health_check"](), "ok")
            self.assertEqual(
                self.tools["get_server_version"](),
                {"revision": "abc123", "environment": "production"},
            )

    def test_system_metrics_reports_expected_shape(self):
        with mocked_system_metrics():
            result = self.tools["get_system_metrics"]()

        self.assertIn("timestamp_utc", result)
        self.assertIsInstance(result["uptime_seconds"], int)
        self.assertGreaterEqual(result["uptime_seconds"], 0)
        self.assertEqual(result["cpu"]["logical_cores"], 4)
        self.assertEqual(result["memory"]["used_bytes"], 60)
        self.assertEqual(result["temperature"]["sensor"], "cpu-thermal")

    @patch("raspberry_mcp.tools.service_logs.run_docker", return_value="one\ntwo\nthree\n")
    def test_logs_keep_recent_lines_and_report_truncation(self, run):
        result = self.tools["get_service_logs"]("jellyfin", lines=2)
        self.assertEqual(result["log_lines"], ["two", "three"])
        self.assertEqual(result["lines_requested"], 2)
        self.assertTrue(result["truncated"])
        run.assert_called_once_with(
            ["container", "logs", "--timestamps", "--tail", "2", "jellyfin"],
            merge_logs=True,
        )

    @patch("raspberry_mcp.tools.service_resources.run_docker")
    @patch("raspberry_mcp.tools.service_resources.inspect_service")
    def test_resources_reject_stopped_container(self, inspect, run):
        inspect.return_value = {"status": "exited"}
        with self.assertRaisesRegex(ValueError, "resource stats require a running"):
            self.tools["get_service_resources"]("jellyfin")
        run.assert_not_called()

    @patch("raspberry_mcp.tools._docker.run_docker")
    def test_status_rejects_malformed_docker_response(self, run):
        run.return_value = "not-json"
        with self.assertRaisesRegex(ValueError, "invalid service state"):
            self.tools["get_service_status"]("jellyfin")

    @patch("raspberry_mcp.tools.storage._volume_info")
    def test_storage_returns_both_configured_volumes(self, volume):
        volume.side_effect = [
            {"label": "internal", "available": True},
            {"label": "external", "available": False, "error": "not mounted"},
        ]
        with patch.dict(
            os.environ,
            {
                "RASPBERRY_MCP_INTERNAL_STORAGE_PATH": "/data",
                "RASPBERRY_MCP_EXTERNAL_STORAGE_PATH": "/media",
            },
        ):
            result = self.tools["get_storage_usage"]()
        self.assertEqual(result["internal"]["label"], "internal")
        self.assertFalse(result["external"]["available"])
        self.assertEqual(volume.call_args_list[0].args, ("internal", "/data"))
        self.assertEqual(volume.call_args_list[1].args, ("external", "/media"))


if __name__ == "__main__":
    unittest.main()
