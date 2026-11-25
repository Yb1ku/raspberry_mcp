#!/usr/bin/env python3
"""Install the minimal, non-secret Raspberry MCP mDNS advertisement."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SERVICE_PATH = "/etc/avahi/services/raspberry-mcp.service"
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "deploy" / "raspberry-mcp.service.template"


def run_ssh(target: str, command: str, *, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", target, command],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "remote command failed"
        raise SystemExit(f"{target}: {detail}")
    return result.stdout.strip()


def render_service(hostname: str, fingerprint: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", hostname):
        raise ValueError("remote hostname contains unsupported characters")
    if not fingerprint.startswith("SHA256:"):
        raise ValueError("SSH fingerprint must use SHA256: format")
    peer_id = f"raspberry-mcp-{hostname}"
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.format(
        peer_id=escape(peer_id), ssh_fingerprint=escape(fingerprint)
    )


def activate(target: str) -> None:
    hostname = run_ssh(target, "hostname --short")
    fingerprint = run_ssh(
        target,
        "ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256 | awk '{print $2}'",
    )
    service = render_service(hostname, fingerprint)
    run_ssh(
        target,
        f"sudo install -o root -g root -m 0644 /dev/stdin {SERVICE_PATH} && "
        "sudo systemctl reload avahi-daemon && "
        "test \"$(systemctl is-active avahi-daemon)\" = active",
        input_text=service,
    )
    print(f"Activated {target}: {SERVICE_PATH} ({hostname}, {fingerprint})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="?", default="pi5", help="SSH alias")
    args = parser.parse_args()
    try:
        activate(args.target)
    except FileNotFoundError:
        print("ssh executable was not found; install OpenSSH client.", file=sys.stderr)
        return 127
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
