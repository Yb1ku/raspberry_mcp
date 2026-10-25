#!/usr/bin/env python3
"""Create deployment records and resolve previously tested immutable images."""

import argparse
import json
import os
import re
import urllib.request


def api(path: str, data: dict | None = None) -> object:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/{path}",
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def pages(path: str):
    for page in range(1, 10001):
        items = api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        if not items:
            return
        yield from items
    raise RuntimeError("Pagination limit exceeded")


def output(name: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise ValueError("Invalid workflow output")
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(f"{name}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["resolve", "begin", "finish"])
    args = parser.parse_args()
    repository = f"ghcr.io/{os.environ['GITHUB_REPOSITORY'].lower()}"
    image = os.environ.get("DEPLOY_IMAGE", "")
    if args.operation != "finish" and not re.fullmatch(
        re.escape(repository) + r"@sha256:[0-9a-f]{64}", image
    ):
        raise ValueError(
            f"Expected {repository}@sha256:<64 lowercase hexadecimal digits>"
        )

    if args.operation == "resolve":
        for deployment in pages("deployments?environment=development"):
            payload = deployment.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            if payload.get("image") != image:
                continue
            if not any(
                status["state"] == "success"
                for status in pages(f"deployments/{deployment['id']}/statuses")
            ):
                continue
            revision = deployment["sha"]
            comparison = api(f"compare/{revision}...main")
            if comparison["status"] not in {"ahead", "identical"}:
                raise ValueError("The tested commit is no longer an ancestor of main")
            output("revision", revision)
            output("image", image)
            return
        raise ValueError("This image has no successful development deployment")

    if args.operation == "begin":
        revision = os.environ["DEPLOY_REVISION"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Expected full commit SHA")
        deployment = api(
            "deployments",
            {
                "ref": revision,
                "environment": os.environ["DEPLOY_ENVIRONMENT"],
                "auto_merge": False,
                "required_contexts": [],
                "production_environment": os.environ["DEPLOY_ENVIRONMENT"]
                == "production",
                "payload": {"image": image},
                "description": f"Deploy {image}",
            },
        )
        output("deployment_id", str(deployment["id"]))
        api(
            f"deployments/{deployment['id']}/statuses",
            {
                "state": "in_progress",
                "log_url": os.environ["DEPLOY_RUN_URL"],
            },
        )
    else:
        deployment_id = os.environ["DEPLOYMENT_ID"]
        if not deployment_id.isdigit():
            raise ValueError("Invalid deployment ID")
        api(
            f"deployments/{deployment_id}/statuses",
            {
                "state": os.environ["DEPLOY_STATE"],
                "log_url": os.environ["DEPLOY_RUN_URL"],
                "auto_inactive": True,
            },
        )


if __name__ == "__main__":
    main()
