# Raspberry MCP

MCP server for controlling and monitoring the Raspberry Pi. The server uses
Streamable HTTP and requires a bearer token for every HTTP request.

## Run locally

Generate a long random token and provide it through the environment. Keep the
token out of the repository and do not paste it into logs or chat:

```sh
export RASPBERRY_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uv run raspberry-mcp
```

The server listens at `http://127.0.0.1:8000/mcp` by default. It exits with an
error if `RASPBERRY_MCP_TOKEN` is missing or blank. Requests without a matching
`Authorization: Bearer <token>` header receive HTTP 401.

To accept connections from another device on a trusted network, set
`RASPBERRY_MCP_HOST` to the Pi's private network address (or `0.0.0.0`) and
optionally set `RASPBERRY_MCP_PORT`. Do not expose plain HTTP to an untrusted
network; use HTTPS or a private encrypted network such as Tailscale.

## Connect Codex

Configure Codex's HTTP MCP server URL as `http://127.0.0.1:8000/mcp` when
Codex runs on the Pi. For a client on another device, use the Pi's reachable
private address instead. In Codex's local `config.toml`, use its environment
variable option so the token itself is not stored in the file:

```toml
[mcp_servers.raspberry_pi]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "RASPBERRY_MCP_TOKEN"
```

Set `RASPBERRY_MCP_TOKEN` in the environment that launches Codex as well as in
the server's environment. These may be different environments even when both
processes run on the same Pi. Keep the credential out of checked-in project
configuration.

This initial shared-token authentication does not identify individual clients
or provide per-tool permissions. Those can be added with OAuth when the server
reaches MVP.

## Read-only tools

- `health_check`: confirms that the authenticated MCP server can answer a tool call.
- `get_system_metrics`: reports CPU temperature, CPU usage and load averages,
  RAM usage, and uptime.
- `get_storage_usage`: reports usage for the internal and external storage mounts.
- `discover_services`: discovers running and stopped Docker containers. Each
  entry includes `name`, `image`, `status`, `health`, `started_at`,
  `time_active_seconds`, `allowed_actions`, network mode and port bindings.
  `started_at` is the last start timestamp, or null if never started. Active
  time is elapsed seconds since the current start (including pauses), or null
  unless running. `allowed_actions` is currently empty because control tools
  and their authorization have not been implemented. This replaces `list_services`.
  The server process needs permission to query the Docker daemon.
- `get_service_status(service_name)`: selected state fields, optional healthcheck
  status, restart count, exit code, OOM flag, and start/finish timestamps. Also
  supports stopped containers. It does not expose environment variables.
- `get_service_logs(service_name, lines=100)`: the last 1–1000 log lines, including
  stdout, stderr and timestamps. Responses are capped at 65536 characters and
  report truncation. Logs may contain sensitive application data.
- `get_service_resources(service_name)`: a snapshot of CPU, RAM, processes/threads,
  and cumulative network and disk I/O counters. Requires a running container.
  CPU can exceed 100% on multiple cores. Byte values are approximate because
  Docker CLI display units are rounded; I/O counters are not transfer rates.
  Network counters are unavailable (`null`) for host-network containers.

Use exact container names from `discover_services`, such as `jellyfin` and
`qbittorrent`. Docker queries time out after 15 seconds and return MCP tool
errors for missing containers or unavailable Docker access. A service without
a configured Docker healthcheck has `health: null`.

Storage paths default to `/` for internal storage and `/mnt/media` for external
storage. Override them with `RASPBERRY_MCP_INTERNAL_STORAGE_PATH` and
`RASPBERRY_MCP_EXTERNAL_STORAGE_PATH` if the Pi uses different mount points.
The tool reports the detected media class (`hdd`, `flash`, or `non_rotational`)
when Linux exposes that information. A non-rotational device is not necessarily
an SSD, so the tool does not claim an exact model type based on that flag alone.
