import os
import unittest
from unittest.mock import patch

from scripts.raspberry_mcp_tunnel import TunnelConfig


class TunnelConfigTests(unittest.TestCase):
    def test_defaults_use_loopback_and_strict_ssh_verification(self):
        with patch.dict(os.environ, {}, clear=True):
            config = TunnelConfig.from_environment()

        self.assertEqual(config.ssh_target, "pi5")
        self.assertEqual(config.command()[-1], "pi5")
        self.assertIn("StrictHostKeyChecking=yes", config.command())
        self.assertIn("127.0.0.1:18000:127.0.0.1:8000", config.command())

    def test_rejects_forwarding_a_non_loopback_remote(self):
        with patch.dict(
            os.environ, {"RASPBERRY_MCP_REMOTE_HOST": "192.168.1.50"}, clear=True
        ), self.assertRaisesRegex(SystemExit, "must remain 127.0.0.1"):
            TunnelConfig.from_environment()

    def test_supports_ip_changes_through_an_ssh_alias_and_identity_file(self):
        with patch.dict(
            os.environ,
            {
                "RASPBERRY_MCP_SSH_TARGET": "pi5",
                "RASPBERRY_MCP_SSH_IDENTITY_FILE": "/run/user/1000/pi5.key",
                "RASPBERRY_MCP_LOCAL_PORT": "18001",
            },
            clear=True,
        ):
            command = TunnelConfig.from_environment().command()

        self.assertEqual(command[-1], "pi5")
        self.assertIn("/run/user/1000/pi5.key", command)
        self.assertIn("127.0.0.1:18001:127.0.0.1:8000", command)


if __name__ == "__main__":
    unittest.main()
