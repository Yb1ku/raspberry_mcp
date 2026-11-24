#!/usr/bin/env python3
"""Deploy an immutable image on the Pi; preserve the previous working service."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from datetime import datetime, timezone

from raspberry_mcp.auth import TOKEN_ENV_VAR, validate_token


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, text=True, capture_output=True)


def inspect(name: str) -> dict | None:
    result = run("docker", "inspect", name, check=False)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def ready(name: str) -> None:
    for _ in range(30):
        info = inspect(name)
        if not info or not info["State"]["Running"]:
            break
        if (
            run(
                "docker",
                "exec",
                name,
                "python",
                "-m",
                "raspberry_mcp.healthcheck",
                check=False,
            ).returncode
            == 0
        ):
            return
        time.sleep(2)
    raise RuntimeError(f"Authenticated MCP readiness check failed: {name}")


def remove(name: str) -> None:
    if inspect(name):
        run("docker", "rm", "-f", name)


def launch(
    name: str, image: str, env_file: Path, target: str, port: int | None
) -> None:
    args = [
        "docker",
        "run",
        "--detach",
        "--name",
        name,
        "--restart",
        "unless-stopped" if port else "no",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--log-opt",
        "max-size=10m",
        "--log-opt",
        "max-file=3",
        "--env-file",
        str(env_file),
        "--env",
        "RASPBERRY_MCP_HOST=0.0.0.0",
        "--env",
        "RASPBERRY_MCP_PORT=8000",
        "--env",
        "RASPBERRY_MCP_HOST_ROOT=/host",
        "--env",
        f"RASPBERRY_MCP_ENVIRONMENT={target}",
        "--mount",
        "type=bind,source=/,target=/host,readonly,bind-propagation=rslave",
        "--mount",
        "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock",
    ]
    if port:
        args.extend(["--publish", f"{port}:8000"])
    run(*args, image)


def write_state(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def deploy(
    target: str,
    image: str,
    revision: str,
    repository: str,
    state_dir: Path,
    env_dir: Path,
) -> None:
    if not re.fullmatch(r"ghcr\.io/[a-z0-9_.-]+/[a-z0-9_.-]+", repository):
        raise ValueError("Invalid GHCR repository")
    if not re.fullmatch(re.escape(repository) + r"@sha256:[0-9a-f]{64}", image):
        raise ValueError(
            "Image must be an immutable digest in the configured repository"
        )
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected a full source commit SHA")
    env_file = env_dir / f"{target}.env"
    if not env_file.is_file() or env_file.stat().st_mode & 0o077:
        raise ValueError(f"Expected a private (0600) environment file: {env_file}")
    token_lines = [
        line.partition("=")[2]
        for line in env_file.read_text().splitlines()
        if line.startswith(f"{TOKEN_ENV_VAR}=")
    ]
    if len(token_lines) != 1:
        raise ValueError(f"Expected exactly one {TOKEN_ENV_VAR} in environment file")
    validate_token(token_lines[0])

    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state_dir / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        name = f"raspberry-mcp-{target}"
        candidate, backup = f"{name}-candidate", f"{name}-previous"
        if inspect(candidate) or inspect(backup):
            raise RuntimeError(
                "An unfinished deployment exists; inspect candidate/previous containers before retrying"
            )
        run("docker", "pull", image)
        metadata = json.loads(run("docker", "image", "inspect", image).stdout)[0]
        if (
            metadata["Config"]
            .get("Labels", {})
            .get("org.opencontainers.image.revision")
            != revision
        ):
            raise ValueError("Image revision label does not match the selected commit")
        if metadata["Architecture"] != "arm64":
            raise ValueError("Deployment requires an ARM64 image")

        # Preflight the exact image, configuration, mounts and MCP auth before downtime.
        try:
            launch(candidate, image, env_file, target, None)
            ready(candidate)
        finally:
            remove(candidate)

        state_file = state_dir / f"{target}.json"
        previous_state = (
            json.loads(state_file.read_text()) if state_file.exists() else None
        )
        previous = inspect(name)
        legacy_unit = f"{name}.service"
        legacy_active = (
            run(
                "systemctl", "is-active", "--quiet", legacy_unit, check=False
            ).returncode
            == 0
        )
        if previous and legacy_active:
            raise RuntimeError(
                "Both legacy and container services are active; resolve before deploying"
            )
        if previous and not previous["State"]["Running"]:
            raise RuntimeError(
                "Previous container is stopped; investigate before deploying"
            )
        if legacy_active:
            # Check noninteractive privilege before changing the running service.
            run("sudo", "-n", "true")

        record = {
            "environment": target,
            "image": image,
            "revision": revision,
            "deployed_at": datetime.now(timezone.utc).isoformat(),
            "actor": os.environ.get("GITHUB_ACTOR", os.environ.get("USER", "unknown")),
            "run_url": os.environ.get("DEPLOY_RUN_URL", ""),
            "previous": {k: v for k, v in previous_state.items() if k != "previous"}
            if previous_state
            else None,
        }
        stopped_legacy = False
        moved_previous = False
        new_started = False
        state_written = False
        try:
            if previous:
                run("docker", "stop", "--time", "15", name)
                run("docker", "rename", name, backup)
                moved_previous = True
            if legacy_active:
                run("sudo", "-n", "systemctl", "stop", legacy_unit)
                stopped_legacy = True
            launch(name, image, env_file, target, 8000 if target == "prod" else 8001)
            new_started = True
            ready(name)
            if legacy_active:
                run("sudo", "-n", "systemctl", "disable", legacy_unit)
            write_state(state_file, record)
            state_written = True
            with (state_dir / "history.jsonl").open("a") as history:
                history.write(json.dumps(record) + "\n")
        except BaseException:
            # Also handle partial docker-run failures (e.g. port allocation).
            if new_started or moved_previous or (previous is None and inspect(name)):
                remove(name)
            if moved_previous:
                run("docker", "rename", backup, name)
                run("docker", "start", name)
                ready(name)
            elif previous and not inspect(name)["State"]["Running"]:
                run("docker", "start", name)
                ready(name)
            if stopped_legacy:
                run("sudo", "-n", "systemctl", "enable", "--now", legacy_unit)
            if state_written:
                if previous_state is None:
                    state_file.unlink(missing_ok=True)
                else:
                    write_state(state_file, previous_state)
            raise

        if moved_previous:
            remove(backup)
        print(json.dumps(record, indent=2))


def main() -> None:
    def interrupted(signum, frame):
        raise SystemExit(f"Deployment interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", choices=["dev", "prod"])
    parser.add_argument("image")
    parser.add_argument("revision")
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=Path.home() / ".local/state/raspberry-mcp"
    )
    parser.add_argument(
        "--env-dir", type=Path, default=Path.home() / ".config/raspberry-mcp"
    )
    args = parser.parse_args()
    try:
        deploy(
            args.environment,
            args.image,
            args.revision,
            args.repository,
            args.state_dir,
            args.env_dir,
        )
    except subprocess.CalledProcessError as exc:
        # Never print docker inspect output or environment file contents on failure.
        raise SystemExit(
            f"Deployment command failed (exit {exc.returncode}); inspect service status on the Pi"
        ) from None


if __name__ == "__main__":
    main()
