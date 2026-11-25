import unittest
from scripts.discover_raspberry_mcp import _fingerprint_from_keyscan, parse_avahi_output


class DiscoveryTests(unittest.TestCase):
    def test_parses_only_annotated_raspberry_mcp_services(self):
        output = (
            '=;eth0;IPv4;Kitchen Pi;_raspberry-mcp._tcp;local;pi-a.local;'
            '192.168.1.50;22;"id=pi-a" "ssh_fingerprint=SHA256:aaa"\n'
            '=;eth0;IPv4;Unknown;_http._tcp;local;unknown.local;192.168.1.60;80;"id=x"\n'
            '=;eth0;IPv4;Unpaired;_raspberry-mcp._tcp;local;pi-b.local;'
            '192.168.1.51;22;"id=pi-b"\n'
        )
        candidates = parse_avahi_output(output)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].peer_id, "pi-a")
        self.assertEqual(candidates[0].address, "192.168.1.50")

    def test_fingerprint_is_derived_from_key_material(self):
        keyscan = "192.168.1.50 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA==\n"
        self.assertTrue(_fingerprint_from_keyscan(keyscan).startswith("SHA256:"))


if __name__ == "__main__":
    unittest.main()
