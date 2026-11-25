#!/usr/bin/env python3
"""Discover and explicitly pair authorized Raspberry MCP peers."""

from __future__ import annotations

import argparse
import base64
import binascii
import csv
import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

SERVICE = "_raspberry-mcp._tcp"
DEFAULT_STORE = Path.home() / ".config" / "raspberry-mcp" / "peers.json"


@dataclass(frozen=True)
class Candidate:
    instance: str
    host: str
    address: str
    port: int
    peer_id: str
    ssh_fingerprint: str


def _properties(fields: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in fields:
        for item in shlex.split(value):
            if "=" in item:
                key, parsed = item.split("=", 1)
                result[key] = parsed
    return result


def parse_avahi_output(output: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for row in csv.reader(output.splitlines(), delimiter=";"):
        if len(row) < 9 or row[0] not in {"=", "+"} or row[4] != SERVICE:
            continue
        try:
            port = int(row[8])
        except ValueError:
            continue
        properties = _properties(row[9:])
        peer_id = properties.get("id", "")
        fingerprint = properties.get("ssh_fingerprint", "")
        if not peer_id or not fingerprint:
            continue
        candidates.append(
            Candidate(row[3], row[6], row[7], port, peer_id, fingerprint)
        )
    return candidates


def discover() -> list[Candidate]:
    try:
        result = subprocess.run(
            ["avahi-browse", "-pr", "-t", SERVICE],
            check=False,
            text=True,
            capture_output=True,
            timeout=8,
        )
    except FileNotFoundError as exc:
        raise SystemExit(
            "avahi-browse is required for local discovery; install Avahi tools."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SystemExit("mDNS discovery timed out; no peer was selected.") from exc
    if result.returncode not in (0, 1):
        raise SystemExit("mDNS discovery failed; no peer was selected.")
    return parse_avahi_output(result.stdout)


def _fingerprint_from_keyscan(output: str) -> str:
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or line.startswith("#"):
            continue
        try:
            key = base64.b64decode(fields[2], validate=True)
        except (ValueError, binascii.Error):
            continue
        digest = base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip("=")
        return f"SHA256:{digest}"
    raise ValueError("ssh-keyscan returned no usable host key")


def verify_host_key(address: str, port: int, expected: str) -> None:
    try:
        result = subprocess.run(
            ["ssh-keyscan", "-T", "5", "-p", str(port), "-t", "ed25519", address],
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("ssh-keyscan is required for pairing.") from exc
    if result.returncode != 0:
        raise SystemExit("Could not read the candidate SSH host key; pairing stopped.")
    try:
        actual = _fingerprint_from_keyscan(result.stdout)
    except ValueError as exc:
        raise SystemExit("Could not read the candidate SSH host key; pairing stopped.") from exc
    if actual != expected:
        raise SystemExit("SSH fingerprint mismatch; pairing stopped.")


def save_pair(candidate: Candidate, store: Path, confirmed: str) -> None:
    if confirmed != candidate.ssh_fingerprint:
        raise SystemExit("The confirmation fingerprint must exactly match the announcement.")
    verify_host_key(candidate.address, candidate.port, confirmed)
    peers: dict[str, dict[str, object]] = {}
    if store.exists():
        try:
            peers = json.loads(store.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot read peer store: {store}") from exc
    peers[candidate.peer_id] = {
        "peer_id": candidate.peer_id,
        "host": candidate.host,
        "address": candidate.address,
        "ssh_port": candidate.port,
        "ssh_fingerprint": candidate.ssh_fingerprint,
        "paired_at": datetime.now(timezone.utc).isoformat(),
    }
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(peers, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(store, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("discover", help="list untrusted mDNS candidates as JSON")
    pair = subparsers.add_parser("pair", help="pair one candidate after fingerprint confirmation")
    pair.add_argument("--id", required=True, dest="peer_id")
    pair.add_argument("--host", required=True)
    pair.add_argument("--address", required=True)
    pair.add_argument("--port", type=int, default=22)
    pair.add_argument("--fingerprint", required=True)
    pair.add_argument("--confirm-fingerprint", required=True)
    pair.add_argument("--store", type=Path, default=DEFAULT_STORE)
    args = parser.parse_args()
    if args.command == "discover":
        print(json.dumps([asdict(item) for item in discover()], indent=2))
        return 0
    candidate = Candidate(args.host, args.host, args.address, args.port, args.peer_id, args.fingerprint)
    save_pair(candidate, args.store, args.confirm_fingerprint)
    print(f"Paired {candidate.peer_id}; stored metadata in {args.store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
