"""Shared, read-only Docker CLI queries."""

import json
import re
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

_SENSITIVE_ERROR_VALUE = re.compile(
    r"(?i)(authorization|password|passwd|secret|token|api[_-]?key|"
    r"access[_-]?key|private[_-]?key)(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)(bearer\s+)[^\s,;]+")


def _safe_error_detail(detail: str) -> str:
    """Keep useful Docker diagnostics while removing common secret values."""
    detail = _BEARER_TOKEN.sub(r"\1[REDACTED]", detail)
    detail = _SENSITIVE_ERROR_VALUE.sub(r"\1\2[REDACTED]", detail)
    return detail.strip()[:1000]


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
        raise ValueError("Cannot query Docker.") from exc

    if result.returncode:
        detail = (result.stdout if merge_logs else result.stderr) or "Docker query failed."
        raise ValueError(_safe_error_detail(detail))
    return result.stdout


def inspect_service(service_name: str) -> dict[str, Any]:
    """Inspect selected state fields without returning container secrets."""
    output = run_docker(["container", "inspect", "--format", _STATUS_FORMAT, service_name])
    try:
        state = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ValueError("Docker returned invalid service state.") from exc
    return {"service_name": service_name, **state}
