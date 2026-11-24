# Diagnostic contract and client verification

This document is the MVP contract for the read-only diagnostic surface exposed
to an Agent through MCP. Lifecycle actions (`start_service`, `stop_service` and
`restart_service`) are deliberately out of scope here.

## Common behaviour

- The MCP endpoint is `POST /mcp` and requires `Authorization: Bearer <token>`.
- Tool names and service names are case-sensitive. Service names must be the
  exact names returned by `discover_services`.
- A Docker failure, missing container, malformed Docker response, or Docker
  timeout is returned as an MCP tool error. A Docker failure must not be
  represented as an empty service list.
- Docker queries have a 15-second subprocess timeout.
- Read-only tools are annotated as idempotent and non-destructive.

## Tool contract

| Tool | Parameters | Successful response | Errors and limits |
| --- | --- | --- | --- |
| `health_check` | None | String `"ok"`. | Authentication is enforced before the tool is called. |
| `get_server_version` | None | Object with `revision` and `environment` strings. Values default to `unknown` and `local` when deployment metadata is absent. | No external dependency. |
| `get_system_metrics` | None | Object with `timestamp_utc`, `temperature`, `cpu`, `memory`, and `uptime_seconds`. Temperature contains `available`, `temperature_celsius`, and `sensor`; unavailable sensors return `null` values. CPU contains usage percentage, logical core count, and 1/5/15-minute load averages. Memory contains total, available, used bytes and used percentage. | Temperature and load average are allowed to be unavailable on a platform; these fields are represented as `null` rather than failing the whole tool. |
| `get_storage_usage` | None | Object with `internal` and `external` volume objects. Each contains `label`, `available`, `mountpoint`; an available volume also contains device, device type, filesystem, total/used/free bytes and used percentage. | Paths default to `/` and `/mnt/media`, configurable with `RASPBERRY_MCP_INTERNAL_STORAGE_PATH` and `RASPBERRY_MCP_EXTERNAL_STORAGE_PATH`. An unmounted or unreadable path returns `available: false` and an `error`, without failing the other volume. |
| `discover_services` | None | Sorted list of service objects: `id`, `name`, `image`, `status`, optional `health`, optional `started_at`, optional `time_active_seconds`, `allowed_actions`, `network_mode`, and `ports`. Stopped containers remain discoverable. | Empty Docker inventory returns `[]`. Docker unavailable, denied, timed out, or malformed output is an MCP error, not `[]`. `started_at` and active time are `null` for never-started containers; active time is only set while running. |
| `get_service_status` | `service_name: string` | Object with `service_name`, `status`, optional `health`, `restart_count`, `exit_code`, `oom_killed`, `started_at`, `finished_at`, and `network_mode`. Stopped containers are supported. | `service_name` must be 1–255 characters matching `[A-Za-z0-9][A-Za-z0-9_.-]*`. Missing containers and Docker failures are MCP errors. Environment variables are never returned. |
| `get_service_resources` | `service_name: string` | Object with `service_name`, `timestamp_utc`, `cpu_percent`, `memory` (`used_bytes`, `limit_bytes`, `used_percent`), `network` (`available`, `mode`, received/sent bytes), `disk_io` (read/written bytes), and `processes_and_threads`. | The container must be running. Host-network containers return `network.available: false` and `null` network counters. Counters are cumulative and byte values are approximate because Docker CLI units are rounded. Missing/invalid stats and Docker failures are MCP errors. |
| `get_service_logs` | `service_name: string`, `lines: int = 100` | Object with `service_name`, `lines_requested`, `lines_returned`, `truncated`, and `log_lines`. Logs include timestamps and both Docker output streams. | `lines` is limited to 1–1000. Output is capped at 65,536 characters; when capped, the most recent characters/lines are retained. Logs can contain application secrets or personal data. Missing containers and Docker failures are MCP errors. |

## Reproducible verification against a deployment

The following checks are read-only and do not start, stop, or restart a
container. They are intentionally independent of the host operating system,
SSH setup, usernames, IP addresses, container names, and deployment platform.

### 1. Configure the MCP client

Configure the Agent with the deployed endpoint and bearer token supplied by
the deployment operator:

```toml
[mcp_servers.raspberry_pi]
url = "https://<MCP_HOST>/mcp"
bearer_token_env_var = "RASPBERRY_MCP_TOKEN"
```

For a private-network deployment, the URL may use `http://` only when the
network itself is trusted or encrypted. The token must be provided through the
client environment and must not be committed or printed.

### 2. Verify authenticated MCP readiness

The client must be able to initialize MCP and call `health_check`, receiving
`"ok"`. Separately, the deployment owner should verify that a request without
or with an incorrect token is rejected with HTTP 401. The method used for that
host-level check is deployment-specific and is deliberately not prescribed by
this contract.

### 3. Run the diagnostic checklist through the Agent

Configure the Agent's MCP server URL for the Pi and provide the bearer token
through its environment. In one session, execute the following calls in order:

1. `health_check` → `"ok"`.
2. `get_server_version` → expected revision and environment (`production`).
3. `get_system_metrics` → current timestamp, non-negative uptime and host
   metrics; temperature may be unavailable.
4. `get_storage_usage` → `internal.available: true`; inspect `external` and
   accept `available: false` only if `/mnt/media` is not mounted.
5. `discover_services` → sorted service list; record one running and, if
   present, one stopped container.
6. `get_service_status` for an exact discovered name → status fields match
   discovery and no environment variables are present.
7. `get_service_logs` with `lines=1` and `lines=1000` → requested/returned
   counts are bounded and `truncated` is meaningful.
8. `get_service_resources` for a running container → resource snapshot is
   returned; for a stopped container, confirm a clear tool error.

Record the revision, environment, service names tested, and any unavailable
mount or sensor in the test result. Do not include tokens or sensitive log
contents in the record.

### 4. Verify negative cases

The Agent/client should also confirm that:

- a missing or incorrect bearer token is rejected;
- an unknown service name produces an MCP tool error;
- `lines=0` and `lines=1001` are rejected by MCP input validation;
- resources for a stopped container produce an error rather than fabricated
  zeroes;
- Docker unavailable or timed out is reported as an error, not an empty list.

The local automated suite covers the deterministic versions of these failure
cases. The Pi checklist is the acceptance test for the deployed host and MCP
client path.
