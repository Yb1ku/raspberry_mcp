"""Discovery must describe stopped containers and never imply authorization."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from raspberry_mcp.tools.services import _discover_services, _service_info


class ServiceDiscoveryTests(unittest.TestCase):
    def setUp(self):
        os.environ["RASPBERRY_MCP_ENABLED_ACTIONS"] = "start,stop,restart"
        os.environ["RASPBERRY_MCP_ALLOWED_SERVICES"] = "jellyfin"
        self.now = datetime(2026, 10, 23, 11, tzinfo=timezone.utc)
        self.container = {
            "id": "abc123", "name": "/jellyfin", "image": "jellyfin/jellyfin",
            "status": "running", "health": "healthy",
            "started_at": "2026-10-23T10:00:00.000000000Z",
            "network_mode": "host", "ports": None,
        }

    def tearDown(self):
        os.environ.pop("RASPBERRY_MCP_ENABLED_ACTIONS", None)
        os.environ.pop("RASPBERRY_MCP_ALLOWED_SERVICES", None)

    def test_running_container_elapsed_time_and_configured_actions(self):
        service = _service_info(self.container, self.now)
        self.assertEqual(service.name, "jellyfin")
        self.assertEqual(service.time_active_seconds, 3600)
        self.assertEqual(service.allowed_actions, ["start", "stop", "restart"])
        self.assertEqual(service.ports, {})

    def test_stopped_container_keeps_last_start_but_has_no_active_time(self):
        self.container.update(status="exited", health=None)
        service = _service_info(self.container, self.now)
        self.assertIsNone(service.time_active_seconds)
        self.assertEqual(service.started_at, self.container["started_at"])
        self.assertIsNone(service.health)

    def test_never_started_container_has_no_start_or_uptime(self):
        self.container.update(status="created", started_at="0001-01-01T00:00:00Z")
        service = _service_info(self.container, self.now)
        self.assertIsNone(service.started_at)
        self.assertIsNone(service.time_active_seconds)

    def test_invalid_timestamp_is_an_error_not_zero_uptime(self):
        self.container["started_at"] = "invalid"
        with self.assertRaisesRegex(ValueError, "start time"):
            _service_info(self.container, self.now)

    @patch("raspberry_mcp.tools.services.run_docker", return_value="")
    def test_empty_docker_does_not_attempt_inspect(self, run):
        self.assertEqual(_discover_services(), [])
        run.assert_called_once()
        self.assertIn("--all", run.call_args.args[0])

    @patch("raspberry_mcp.tools.services.run_docker", side_effect=ValueError("Access denied"))
    def test_unavailable_docker_is_not_reported_as_empty_inventory(self, run):
        with self.assertRaisesRegex(ValueError, "Access denied"):
            _discover_services()


if __name__ == "__main__":
    unittest.main()
