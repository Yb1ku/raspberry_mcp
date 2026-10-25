"""Exercise promotion eligibility and deployment rollback without a Docker daemon."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import deploy, deployment_record


REPOSITORY = "ghcr.io/yb1ku/raspberry_mcp"
IMAGE = REPOSITORY + "@sha256:" + "a" * 64
REVISION = "b" * 40


class DeploymentTests(unittest.TestCase):
    def exercise(self, fail_on: str | None = None, legacy: bool = False):
        containers = (
            {}
            if legacy
            else {"raspberry-mcp-prod": {"State": {"Running": True}, "old": True}}
        )
        operations = []

        def run(*args, check=True):
            operations.append(args)
            if args[:3] == ("docker", "image", "inspect"):
                return subprocess.CompletedProcess(
                    args,
                    0,
                    json.dumps(
                        [
                            {
                                "Architecture": "arm64",
                                "Config": {
                                    "Labels": {
                                        "org.opencontainers.image.revision": REVISION
                                    }
                                },
                            }
                        ]
                    ),
                    "",
                )
            if args[:2] == ("systemctl", "is-active"):
                return subprocess.CompletedProcess(args, 0 if legacy else 3, "", "")
            if args[:2] == ("docker", "rename"):
                containers[args[3]] = containers.pop(args[2])
            if args[:2] == ("docker", "stop"):
                containers[args[-1]]["State"]["Running"] = False
            if args[:2] == ("docker", "start"):
                containers[args[-1]]["State"]["Running"] = True
            if args[:3] == ("docker", "rm", "-f"):
                containers.pop(args[3])
            return subprocess.CompletedProcess(args, 0, "", "")

        def launch(name, image, env_file, target, port):
            containers[name] = {"State": {"Running": True}}

        def ready(name):
            if fail_on == name and not containers[name].get("old"):
                raise RuntimeError("probe failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "prod.env").write_text("RASPBERRY_MCP_TOKEN=test-only\n")
            (root / "prod.env").chmod(0o600)
            with (
                patch.object(deploy, "run", side_effect=run),
                patch.object(
                    deploy, "inspect", side_effect=lambda name: containers.get(name)
                ),
                patch.object(deploy, "launch", side_effect=launch),
                patch.object(deploy, "ready", side_effect=ready),
            ):
                if fail_on:
                    with self.assertRaisesRegex(RuntimeError, "probe failed"):
                        deploy.deploy(
                            "prod", IMAGE, REVISION, REPOSITORY, root / "state", root
                        )
                    self.assertFalse((root / "state/prod.json").exists())
                else:
                    deploy.deploy(
                        "prod", IMAGE, REVISION, REPOSITORY, root / "state", root
                    )
                    self.assertEqual(
                        json.loads((root / "state/prod.json").read_text())["image"],
                        IMAGE,
                    )
        return containers, operations

    def test_preflight_failure_keeps_production_running(self):
        containers, operations = self.exercise(fail_on="raspberry-mcp-prod-candidate")
        self.assertTrue(containers["raspberry-mcp-prod"]["old"])
        self.assertFalse(any(args[:2] == ("docker", "stop") for args in operations))

    def test_failed_deploy_restores_previous_container(self):
        containers, _ = self.exercise(fail_on="raspberry-mcp-prod")
        self.assertEqual(list(containers), ["raspberry-mcp-prod"])
        self.assertTrue(containers["raspberry-mcp-prod"]["old"])
        self.assertTrue(containers["raspberry-mcp-prod"]["State"]["Running"])

    def test_failed_first_migration_restores_systemd_service(self):
        containers, operations = self.exercise(
            fail_on="raspberry-mcp-prod", legacy=True
        )
        self.assertFalse(containers)
        self.assertIn(
            (
                "sudo",
                "-n",
                "systemctl",
                "enable",
                "--now",
                "raspberry-mcp-prod.service",
            ),
            operations,
        )

    def test_success_records_image_and_removes_backup(self):
        containers, _ = self.exercise()
        self.assertEqual(list(containers), ["raspberry-mcp-prod"])
        self.assertNotIn("old", containers["raspberry-mcp-prod"])

    def test_mutable_tag_is_rejected_before_docker_access(self):
        with patch.object(deploy, "run") as run:
            with self.assertRaisesRegex(ValueError, "immutable digest"):
                deploy.deploy(
                    "prod",
                    REPOSITORY + ":latest",
                    REVISION,
                    REPOSITORY,
                    Path("/unused"),
                    Path("/unused"),
                )
            run.assert_not_called()


class PromotionEligibilityTests(unittest.TestCase):
    def resolve(self, statuses, comparison="ahead"):
        deployment = {"id": 7, "sha": REVISION, "payload": {"image": IMAGE}}

        def pages(path):
            return iter([deployment] if path.startswith("deployments?") else statuses)

        with (
            patch.dict(
                os.environ,
                {"GITHUB_REPOSITORY": "Yb1ku/raspberry_mcp", "DEPLOY_IMAGE": IMAGE},
            ),
            patch("sys.argv", ["deployment_record.py", "resolve"]),
            patch.object(deployment_record, "pages", side_effect=pages),
            patch.object(deployment_record, "api", return_value={"status": comparison}),
            patch.object(deployment_record, "output") as output,
        ):
            deployment_record.main()
            return output.call_args_list

    def test_historical_success_is_promotable_even_if_now_inactive(self):
        outputs = self.resolve([{"state": "inactive"}, {"state": "success"}])
        self.assertEqual(outputs[0].args, ("revision", REVISION))

    def test_failed_dev_deployment_is_not_promotable(self):
        with self.assertRaisesRegex(ValueError, "no successful"):
            self.resolve([{"state": "failure"}])

    def test_commit_removed_from_main_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ancestor"):
            self.resolve([{"state": "success"}], comparison="diverged")
