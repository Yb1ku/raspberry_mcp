"""Lifecycle actions must enforce policy and use only fixed Docker commands."""

import os
import threading
import unittest
from unittest.mock import patch

from raspberry_mcp.tools.service_actions import (
    _run_lifecycle_action,
    allowed_actions_for_service,
    enabled_actions,
)


class ServiceActionTests(unittest.TestCase):
    def setUp(self):
        os.environ["RASPBERRY_MCP_ENABLED_ACTIONS"] = "start,stop,restart"
        os.environ["RASPBERRY_MCP_ALLOWED_SERVICES"] = "jellyfin"

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

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_restart_stopped_service_must_end_running(self, run, inspect):
        inspect.side_effect = [{"status": "exited"}, {"status": "running"}]

        result = _run_lifecycle_action("jellyfin", "restart")

        self.assertTrue(result["changed"])
        self.assertEqual(result["previous_status"], "exited")
        self.assertEqual(result["status"], "running")
        run.assert_called_once_with(["container", "restart", "jellyfin"])

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_action_fails_when_post_state_is_not_reached(self, run, inspect):
        inspect.side_effect = [{"status": "exited"}, {"status": "exited"}]

        with self.assertRaisesRegex(ValueError, "expected state 'running'"):
            _run_lifecycle_action("jellyfin", "start")

        run.assert_called_once_with(["container", "start", "jellyfin"])

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_missing_service_propagates_a_docker_error(self, run, inspect):
        os.environ["RASPBERRY_MCP_ALLOWED_SERVICES"] = "jellyfin,missing"
        inspect.side_effect = ValueError("No such container: missing")

        with self.assertRaisesRegex(ValueError, "No such container"):
            _run_lifecycle_action("missing", "start")

        run.assert_not_called()

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_docker_unavailable_is_returned_as_an_error(self, run, inspect):
        inspect.side_effect = ValueError("Docker CLI is not installed.")

        with self.assertRaisesRegex(ValueError, "Docker CLI"):
            _run_lifecycle_action("jellyfin", "stop")

        run.assert_not_called()

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_docker_timeout_during_action_is_returned_as_an_error(self, run, inspect):
        inspect.return_value = {"status": "exited"}
        run.side_effect = ValueError("Docker query timed out after 15 seconds.")

        with self.assertRaisesRegex(ValueError, "timed out"):
            _run_lifecycle_action("jellyfin", "start")

    @patch("raspberry_mcp.tools.service_actions.inspect_service")
    @patch("raspberry_mcp.tools.service_actions.run_docker")
    def test_operations_for_one_service_are_serialized(self, run, inspect):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def docker_call(arguments):
            calls.append(arguments)
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(1))

        run.side_effect = docker_call
        inspect.side_effect = lambda _service: {
            "status": "exited" if inspect.call_count == 1 else "running"
        }
        results = []

        first = threading.Thread(
            target=lambda: results.append(_run_lifecycle_action("jellyfin", "start"))
        )
        second = threading.Thread(
            target=lambda: results.append(_run_lifecycle_action("jellyfin", "start"))
        )
        first.start()
        self.assertTrue(entered.wait(1))
        second.start()
        self.assertEqual(len(calls), 1)
        release.set()
        first.join(1)
        second.join(1)

        self.assertEqual(len(results), 2)
        self.assertEqual(calls, [["container", "start", "jellyfin"]])
        self.assertEqual(sorted(result["changed"] for result in results), [False, True])

    def test_unknown_action_cannot_construct_a_docker_command(self):
        with self.assertRaisesRegex(ValueError, "not enabled"):
            _run_lifecycle_action("jellyfin", "exec")

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

    def test_missing_policy_denies_lifecycle_actions_by_default(self):
        os.environ.pop("RASPBERRY_MCP_ENABLED_ACTIONS")
        os.environ.pop("RASPBERRY_MCP_ALLOWED_SERVICES")
        self.assertEqual(enabled_actions(), [])
        self.assertEqual(allowed_actions_for_service("jellyfin"), [])
        with self.assertRaisesRegex(ValueError, "not allowed"):
            _run_lifecycle_action("jellyfin", "start")

    def test_unknown_configured_action_is_rejected(self):
        os.environ["RASPBERRY_MCP_ENABLED_ACTIONS"] = "start,exec"
        with self.assertRaisesRegex(ValueError, "unsupported actions"):
            enabled_actions()


if __name__ == "__main__":
    unittest.main()
