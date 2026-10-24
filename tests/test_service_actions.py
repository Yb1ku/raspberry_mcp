"""Lifecycle actions must enforce policy and use only fixed Docker commands."""

import os
import unittest
from unittest.mock import patch

from raspberry_mcp.tools.service_actions import (
    _run_lifecycle_action,
    allowed_actions_for_service,
    enabled_actions,
)


class ServiceActionTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("RASPBERRY_MCP_ENABLED_ACTIONS", None)
        os.environ.pop("RASPBERRY_MCP_ALLOWED_SERVICES", None)

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_start_running_service_is_idempotent(self, run, inspect):
        inspect.return_value = {"status": "running"}
        result = _run_lifecycle_action("jellyfin", "start")
        self.assertFalse(result["changed"])
        run.assert_not_called()
        inspect.assert_called_once_with("jellyfin")

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_stop_running_service_inspects_after_action(self, run, inspect):
        inspect.side_effect = [{"status": "running"}, {"status": "exited"}]
        result = _run_lifecycle_action("jellyfin", "stop")
        self.assertTrue(result["changed"])
        run.assert_called_once_with(["container", "stop", "jellyfin"])
        self.assertEqual(result["status"], "exited")

    def test_policy_can_limit_actions_and_services(self):
        os.environ["RASPBERRY_MCP_ENABLED_ACTIONS"] = "start,restart"
        os.environ["RASPBERRY_MCP_ALLOWED_SERVICES"] = "jellyfin"
        self.assertEqual(enabled_actions(), ["start", "restart"])
        self.assertEqual(allowed_actions_for_service("jellyfin"), ["start", "restart"])
        self.assertEqual(allowed_actions_for_service("qbittorrent"), [])
        with self.assertRaisesRegex(ValueError, "not enabled"):
            _run_lifecycle_action("jellyfin", "stop")
        with self.assertRaisesRegex(ValueError, "not allowed"):
            _run_lifecycle_action("qbittorrent", "start")

    def test_unknown_configured_action_is_rejected(self):
        os.environ["RASPBERRY_MCP_ENABLED_ACTIONS"] = "start,exec"
        with self.assertRaisesRegex(ValueError, "unsupported actions"):
            enabled_actions()


if __name__ == "__main__":
    unittest.main()
