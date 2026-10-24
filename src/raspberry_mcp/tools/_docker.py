"""Shared, read-only Docker CLI queries."""

import json
import subprocess
from typing import Annotated, Any

from pydantic import Field


ServiceName = Annotated[
    str,
    Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", min_length=1, max_length=255),
]

_STATUS_FORMAT = (
    '{"status":{{json .State.Status}},'
    '"health":{{with index .State "Health"}}{{json .Status}}{{else}}null{{end}},'
    '"restart_count":{{json .RestartCount}},'
    '"exit_code":{{json .State.ExitCode}},'
    '"oom_killed":{{json .State.OOMKilled}},'
    '"started_at":{{json .State.StartedAt}},'
    '"finished_at":{{json .State.FinishedAt}},'
    '"network_mode":{{json .HostConfig.NetworkMode}}}'
)


def run_docker(arguments: list[str], *, merge_logs: bool = False) -> str:
    """Run a fixed Docker query with a timeout and readable errors."""
    try:
        result = subprocess.run(
            ["docker", *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_logs else subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise ValueError("Docker CLI is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Docker query timed out after 15 seconds.") from exc
    except OSError as exc:
        raise ValueError(f"Cannot query Docker: {exc}") from exc

    if result.returncode:
        detail = (result.stdout if merge_logs else result.stderr) or "Docker query failed."
        raise ValueError(detail.strip()[:1000])
    return result.stdout


def inspect_service(service_name: str) -> dict[str, Any]:
    """Inspect selected state fields without returning container secrets."""
    output = run_docker(["container", "inspect", "--format", _STATUS_FORMAT, service_name])
    try:
        state = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError("Docker returned invalid service state.") from exc
    return {"service_name": service_name, **state}
