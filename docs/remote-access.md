# Remote Agent access to the Raspberry MCP

The supported remote transport is an SSH local forward. The MCP remains bound
to `127.0.0.1:8000` on the Raspberry, and the Agent talks to a local listener
such as `127.0.0.1:18000`. No MCP port is published on the LAN or Internet.

The SSH connection supplies encrypted transport and a verifiable Raspberry
identity through the SSH host key in `~/.ssh/known_hosts`. The MCP bearer token
is still required at the forwarded endpoint and is supplied through the
Agent's environment, never through this repository or command arguments.

## Discover a Raspberry

`scripts/discover_raspberry_mcp.py` performs limited local discovery through
the `_raspberry-mcp._tcp` mDNS service. An announcement is only a candidate:
it must contain a stable peer ID and an advertised SSH fingerprint. Discovery
never selects a peer, changes SSH configuration, or sends a Bearer token.

```sh
uv run python scripts/discover_raspberry_mcp.py discover
```

Review the candidates and verify the selected fingerprint through a trusted
out-of-band channel. Pair only after that human confirmation:

```sh
uv run python scripts/discover_raspberry_mcp.py pair \
  --id pi-a --host pi-a.local --address 192.168.1.50 --port 22 \
  --fingerprint 'SHA256:...' --confirm-fingerprint 'SHA256:...'
```

Pairing re-reads the live Ed25519 SSH key with `ssh-keyscan`, compares its
derived fingerprint exactly, and stores only peer metadata in
`~/.config/raspberry-mcp/peers.json` with mode `0600`. It stores no token or
private key. On a later discovery, the same peer ID and fingerprint may have a
new address; update the local SSH alias/hostname only after the same identity
check. A changed fingerprint is an identity failure, not an IP change.

The Raspberry's mDNS advertisement must include `id=<stable-id>` and
`ssh_fingerprint=SHA256:<ed25519-host-key-fingerprint>`. Do not advertise a
Bearer token. If Avahi is unavailable, use the preconfigured SSH alias from
the one-time setup; do not broaden discovery to arbitrary LAN hosts.

The reproducible activation command is run from this checkout by an authorized
operator:

```sh
uv run python scripts/activate_raspberry_mdns.py pi5
```

It reads the Raspberry hostname and SSH host-key fingerprint remotely, installs
`/etc/avahi/services/raspberry-mcp.service` with root ownership and mode `0644`,
then reloads Avahi and checks that it is active. The service is persistent and
contains no bearer token or private key.

## One-time host setup

Use a stable SSH config alias rather than an IP in Agent configuration. The
alias may resolve through local DNS, DHCP reservation, or the existing `pi5`
entry. A changed IP is therefore handled by SSH configuration/DNS. A changed
host key is rejected and must be investigated; do not bypass verification with
`StrictHostKeyChecking=no`.

The SSH account should be a dedicated non-root account with a public key in
the Raspberry user's `authorized_keys`. Limit that key to port forwarding if
the operational SSH policy permits it. The private key stays in the OS SSH
agent or an untracked file with restrictive permissions.

Before using the tunnel, verify the host key once over the authorized network:

```sh
ssh -o StrictHostKeyChecking=ask pi5 true
```

Only accept the fingerprint through a trusted out-of-band check. Subsequent
connections use strict verification and fail closed if the key changes.

## Start the tunnel

From the device running Agent/Codex:

```sh
export RASPBERRY_MCP_SSH_TARGET=pi5
export RASPBERRY_MCP_LOCAL_PORT=18000
uv run python scripts/raspberry_mcp_tunnel.py
```

If the key is not already selected by `~/.ssh/config`, set the path through
`RASPBERRY_MCP_SSH_IDENTITY_FILE` (the value is not written to the repository).
The script uses `BatchMode`, `ExitOnForwardFailure`, keepalives, strict host-key
checking, and a loopback-only local bind. Stop it with `Ctrl-C`; a lost network
causes SSH to terminate instead of leaving a false-ready MCP endpoint.

Configure the Agent's MCP URL as `http://127.0.0.1:18000/mcp` and provide
`RASPBERRY_MCP_TOKEN` from the private runtime environment. The token must match
the token loaded by the Raspberry MCP deployment. Do not put it in `config.toml`.

## Failure meanings and recovery

- **Pi absent / SSH unavailable:** the tunnel exits or cannot be created. Check
  network reachability, SSH service, alias resolution, and the host key; the
  Agent must report the MCP as unavailable and take no lifecycle action.
- **MCP unavailable on the Pi:** SSH may connect but
  `ExitOnForwardFailure` only proves the TCP forward. An authenticated MCP
  `initialize` followed by `health_check` must pass before using tools. Inspect
  the container/service locally on the Pi; do not expose another port.
- **Network lost:** SSH keepalives detect the loss and the tunnel closes. Retry
  only after the network is authorized and the host key still matches.
- **Bearer token rejected:** HTTP 401 means the transport is up but the MCP
  credential is wrong or stale. Rotate/update the private runtime secret through
  the existing deployment procedure; never print or commit the token.
- **Identity unknown:** discard the candidate and do not add it to
  `known_hosts` or the paired-peer store until its fingerprint is confirmed.
- **Pi powered off:** discovery returns no usable candidate; retain the last
  paired metadata but do not retry lifecycle actions automatically.

## Safe verification

The command construction and discovery parsing are covered by
`tests/test_remote_tunnel.py` and `tests/test_discover_raspberry_mcp.py`. A
live check is intentionally environment-specific:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes pi5 true
uv run python scripts/discover_raspberry_mcp.py discover
uv run python scripts/raspberry_mcp_tunnel.py
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${RASPBERRY_MCP_TOKEN}" \
  http://127.0.0.1:18000/mcp
```

Do not run the live check with an unset token, and do not include the token in
logs or captured output. The repository's existing MCP protocol validation
remains the source of truth for the `initialize` and `health_check` sequence.
