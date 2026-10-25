#!/usr/bin/env python3
"""Show recorded and actually running deployment versions on the Pi."""

import json
from pathlib import Path

from deploy import inspect, run


for target in ("dev", "prod"):
    path = Path.home() / f".local/state/raspberry-mcp/{target}.json"
    container = inspect(f"raspberry-mcp-{target}")
    state = json.loads(path.read_text()) if path.exists() else None
    legacy = run(
        "systemctl", "is-active", f"raspberry-mcp-{target}.service", check=False
    ).stdout.strip()
    print(
        json.dumps(
            {
                "environment": target,
                "recorded": state,
                "container": {
                    "image": container["Config"]["Image"],
                    "status": container["State"]["Status"],
                    "health": container["State"].get("Health", {}).get("Status"),
                    "revision": container["Config"]
                    .get("Labels", {})
                    .get("org.opencontainers.image.revision"),
                }
                if container
                else None,
                "legacy_service": legacy,
            },
            indent=2,
        )
    )
