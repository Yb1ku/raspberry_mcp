import unittest

from scripts.activate_raspberry_mdns import render_service


class MdnsServiceTests(unittest.TestCase):
    def test_render_contains_only_identity_and_ssh_port(self):
        service = render_service("pi5-node", "SHA256:abc")
        self.assertIn("_raspberry-mcp._tcp", service)
        self.assertIn("<port>22</port>", service)
        self.assertIn("id=raspberry-mcp-pi5-node", service)
        self.assertIn("ssh_fingerprint=SHA256:abc", service)
        self.assertNotIn("RASPBERRY_MCP_TOKEN", service)

    def test_rejects_unsafe_hostname(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            render_service("pi; curl evil", "SHA256:abc")


if __name__ == "__main__":
    unittest.main()
