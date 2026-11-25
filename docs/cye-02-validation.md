# CYE-02: MVP validation on the Raspberry Pi

Validation performed on `192.168.1.50` on 2026-11-24 (Europe/Madrid), using
the authenticated MCP client bundled in the development container. The Agent
was not directly connected to this MCP endpoint in this execution environment;
the protocol-level client run below is the reproducible equivalent.

## Deployment evidence

- Host: `pi5-node`, `aarch64`.
- Dev container: `raspberry-mcp-dev`, `running`, `healthy`.
- Production container: `raspberry-mcp-prod`, `running`, `healthy`.
- Dev and production image digest:
  `sha256:b9c6a6cc8b97bbac769b0b6aa680a32c6039c3d87287fb91a1c8a7ef24704beb`.
- Reported revision: `7fa8825276b14f1a2cd3239c5cab29fb55d5e740`.
- Dev host endpoint: `http://192.168.1.50:8001/mcp`.
- Production host endpoint: `http://192.168.1.50:8000/mcp`.

The runtime token was read only inside the dev container. It was not printed,
stored, or included in this document.

SSH access uses the configured `pi5` alias (`ybiku` with `~/.ssh/pi5key`).
Connecting directly to `192.168.1.50` selects the local default user and keys,
which explains the earlier authentication rejection; it was not a network or
Raspberry outage.

The latest runtime re-check through that alias found ARM64 dev with digest
`sha256:364a4ad394e4dbe027b19c9ece42684487a8fde7f2d1e04d912cd008efd66814`
and revision `92f5355ef6edea1a5f6fc6ad83592a1922597b04` (current `main`). The
authenticated MCP client completed initialization, tool discovery, health,
version, metrics, storage, service discovery, status, logs, and resources;
missing-service handling errored as expected, and missing/invalid tokens
returned HTTP 401. This evidence is for `main`, not local `db0ce16`.

## MCP protocol validation

The authenticated client performed `initialize`, `tools/list`, and these calls
against dev:

- `health_check`: `ok`.
- `get_server_version`: environment `dev`, revision as above.
- `get_system_metrics`: returned CPU temperature, CPU/load, memory and uptime.
- `get_storage_usage`: returned internal flash and external HDD volumes.
- `discover_services`: returned the Docker service inventory.
- `get_service_status`: succeeded for `jellyfin`, `qbittorrent`, both MCP
  containers and the stopped `pensive_chaplygin` container.
- `get_service_logs`: succeeded for the same services with a five-line limit.
- `get_service_resources`: succeeded for running services and correctly
  returned a tool error for the stopped container.

The server advertised the expected read-only and lifecycle tools:
`health_check`, `get_server_version`, `get_system_metrics`,
`get_storage_usage`, `discover_services`, `get_service_status`,
`get_service_logs`, `get_service_resources`, `start_service`, `stop_service`,
and `restart_service`.

## Authentication and negative cases

Requests to the dev endpoint without an `Authorization` header and with an
invalid bearer token both returned HTTP `401`. A diagnostic call for the
nonexistent service `definitely-not-a-real-service` returned an MCP tool error
without changing container state.

## Lifecycle control result

No `start_service`, `stop_service`, or `restart_service` call was made. The
dev container has no explicit `RASPBERRY_MCP_ALLOWED_SERVICES` or
`RASPBERRY_MCP_ENABLED_ACTIONS` configuration, so the observed inventory
reported lifecycle actions for every Docker container. The Pi has no isolated
application canary: the visible candidates are `jellyfin`, `qbittorrent`, the
two MCP containers, and an exited `hello-world` container with a generated
name. Consequently there is no service that satisfies both “allowed canary”
and “safe, reversible operation”. This is a deliberate safety block, not a
failed MCP test.

To complete the lifecycle part, provision a disposable dev-only canary and
configure both allowlists explicitly for that container. Record its state,
run one reversible transition at a time, and verify the previous/resulting
state through `get_service_status`. Do not use production or the media
services as a substitute.

## Reproducible protocol procedure

Run from the Pi, without printing the token:

```sh
docker exec -i raspberry-mcp-dev python - <<'PY'
import asyncio, os
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    async with httpx2.AsyncClient(
        headers={"Authorization": "Bearer " + os.environ["RASPBERRY_MCP_TOKEN"]}
    ) as client:
        async with streamable_http_client(
            "http://127.0.0.1:8000/mcp", http_client=client
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print([tool.name for tool in (await session.list_tools()).tools])
                for name, args in [
                    ("health_check", {}),
                    ("get_server_version", {}),
                    ("get_system_metrics", {}),
                    ("get_storage_usage", {}),
                    ("discover_services", {}),
                ]:
                    print(name, await session.call_tool(name, args))

asyncio.run(main())
PY
```

For HTTP authentication checks, use the published dev port and inspect only
the status code:

```sh
curl -o /dev/null -sS -w '%{http_code}\n' -X POST \
  http://127.0.0.1:8001/mcp -H 'Content-Type: application/json' --data '{}'
curl -o /dev/null -sS -w '%{http_code}\n' -X POST \
  http://127.0.0.1:8001/mcp -H 'Authorization: Bearer invalid-token-for-test' \
  -H 'Content-Type: application/json' --data '{}'
```

Both commands should print `401`.

## Acceptance status

- ARM64 image deployed and dev healthy: **pass** (current `main` runtime;
  the `db0ce16` candidate was also built and healthy on the ARM64 host).
- Authenticated MCP diagnostics: **pass**.
- Invalid/missing authentication rejection: **pass**.
- Production and non-participating services remained healthy: **pass**;
  no lifecycle mutation was performed.
- Agent direct connection: **not available here**; equivalent MCP protocol
  validation recorded.
- Safe lifecycle action on an allowed canary: **pass** in an isolated,
  disposable canary with explicit `start,stop,restart` and service allowlists;
  the canary and candidate containers were removed after verification.

## Current-branch revalidation

The current checkout is branch `mvp-initial-version` at commit
`db0ce16` (`Fix deployment script imports`). The live evidence above must not
be attributed to this commit: the deployed dev image reports the separate
`main` revision `92f5355ef6edea1a5f6fc6ad83592a1922597b04`.

Local source verification for `db0ce16` completed with:

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
```

Result: 51 tests passed, including authentication, diagnostics, service
actions/allowlists, and deployment rollback/promotion checks. Because the
local Docker daemon is unavailable under the Snap confinement, the exact
`db0ce16` source was archived to the Pi and built there as an ARM64 candidate
with image revision label `db0ce16`. The candidate passed authenticated
diagnostics, invalid/missing authentication checks, service status/logs, and
the full lifecycle sequence against an isolated `cye02-canary`; production and
the deployed dev container were not changed. The candidate image and canary
 were removed after the test.

## Dev image re-check on 2026-11-25

The development deployment was updated on 2026-11-24 at 16:43 Europe/Madrid
and is still running healthy. Its immutable image is
`sha256:364a4ad394e4dbe027b19c9ece42684487a8fde7f2d1e04d912cd008efd66814`
with revision `92f5355ef6edea1a5f6fc6ad83592a1922597b04`.

Against that deployed image, the authenticated client repeated tool discovery,
health, version, system metrics, storage, service discovery, status, logs, and
resources successfully. Missing and invalid authentication returned 401, and
a nonexistent service returned an MCP tool error. A candidate from the same
digest, with an explicit allowlist for a disposable canary, passed the
`start`, `stop`, `restart`, and final `stop` transitions; repeated `stop` was
idempotent and a lifecycle call for `jellyfin` was rejected. Temporary
candidates and the canary were removed; dev and prod remained healthy.

## Direct Agent re-check on 2026-11-25

An ephemeral Codex Agent session connected directly to the configured
`raspberry_pi` MCP server at the dev endpoint, using the token only through an
environment variable and without persisting MCP configuration. It confirmed
revision `92f5355ef6edea1a5f6fc6ad83592a1922597b04` and successfully called
`health_check`, `get_server_version`, `get_system_metrics`,
`get_storage_usage`, `discover_services`, `get_service_status` for Jellyfin,
`get_service_logs` with five lines, and `get_service_resources`. Jellyfin was
reported `running/healthy`; no lifecycle actions were invoked and no state was
changed. The Agent session could not expose `initialize`/`tools/list` as
separate calls or safely submit invalid credentials; those cases remain covered
by the direct protocol checks above.
