#!/usr/bin/env python3
"""Open a fail-closed SSH tunnel to the Raspberry MCP endpoint.

The MCP stays bound to loopback on the Raspberry. The Agent connects to the
local loopback listener created by this script, so no MCP port is published on
the LAN. SSH host-key verification and public-key authentication provide the
transport identity; the MCP bearer token remains a separate runtime secret.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass


def _port(name: str, default: int) -> int:
    value = os.environ.get(name, str(default))
    try:
        result = int(value)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer.") from exc
    if not 1 <= result <= 65535:
        raise SystemExit(f"{name} must be between 1 and 65535.")
    return result


@dataclass(frozen=True)
class TunnelConfig:
    ssh_target: str
    remote_host: str
    remote_port: int
    local_host: str
    local_port: int
    identity_file: str | None = None

    @classmethod
    def from_environment(cls) -> "TunnelConfig":
        target = os.environ.get("RASPBERRY_MCP_SSH_TARGET", "pi5").strip()
        if not target or any(char.isspace() for char in target):
            raise SystemExit(
                "RASPBERRY_MCP_SSH_TARGET must be a non-empty SSH config alias."
            )
        remote_host = os.environ.get("RASPBERRY_MCP_REMOTE_HOST", "127.0.0.1")
        if remote_host != "127.0.0.1":
            raise SystemExit(
                "RASPBERRY_MCP_REMOTE_HOST must remain 127.0.0.1 to avoid forwarding "
                "the Pi's LAN beyond the MCP service."
            )
        identity = os.environ.get("RASPBERRY_MCP_SSH_IDENTITY_FILE")
        return cls(
            ssh_target=target,
            remote_host=remote_host,
            remote_port=_port("RASPBERRY_MCP_REMOTE_PORT", 8000),
            local_host=os.environ.get("RASPBERRY_MCP_LOCAL_HOST", "127.0.0.1"),
            local_port=_port("RASPBERRY_MCP_LOCAL_PORT", 18000),
            identity_file=identity or None,
        )

    def command(self) -> list[str]:
        command = [
            "ssh",
            "-N",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            "-L",
            f"{self.local_host}:{self.local_port}:{self.remote_host}:{self.remote_port}",
        ]
        if self.identity_file:
            command.extend(["-i", self.identity_file, "-o", "IdentitiesOnly=yes"])
        command.append(self.ssh_target)
        return command


def main() -> int:
    config = TunnelConfig.from_environment()
    command = config.command()
    print(
        "Opening authenticated SSH tunnel "
        f"127.0.0.1:{config.local_port} -> {config.ssh_target}:"
        f"{config.remote_host}:{config.remote_port}"
    )
    print("SSH host-key verification is required; no MCP port is exposed on the LAN.")
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError:
        print("ssh executable was not found; install OpenSSH client.", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
