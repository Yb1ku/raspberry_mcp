# Image deployment runbook

Development is an environment, not a branch. Work in feature branches in the
configured project checkout and open pull requests against `main`.
Merging a PR builds an ARM64 image from the merged commit and deploys it to the
shared test environment. Uncommitted source files and branch switches never
change a deployed container.

This is an operator runbook. Values such as the host, account, filesystem
paths, ports, container names, and runner directory are deployment parameters;
they are intentionally shown as placeholders and are not part of the MCP
client contract.

## Workflows

- **Pull request checks** runs unit tests and a container startup/authentication probe on
  GitHub-hosted runners for pull requests. It never uses the Pi runner.
- **Build image and deploy dev** runs after pushes to `main` (including merges),
  or manually on `main`. It tests the source, builds `linux/arm64`, and pushes
  `ghcr.io/yb1ku/raspberry_mcp:sha-<full-commit>` using `GITHUB_TOKEN`.
  Deployment uses the build's immutable `@sha256:...` digest, not that tag.
- **Promote image to production** is manual, from `main`, with one input:
  `image`, the full `ghcr.io/yb1ku/raspberry_mcp@sha256:...` reference.
  It looks up a successful **development** deployment of that exact digest
  and verifies that its commit is still an ancestor of `main`. Failed, unknown,
  or mutable image references are rejected. Older successful dev images remain
  selectable even after newer versions have replaced them. No rebuild occurs.
- **Deploy immutable image** is the shared deployment implementation. Both
  callers share a concurrency group. Deployments are never cancelled to start
  another deployment. Superseded dev builds are skipped when their commit is
  no longer the head of `main`. GitHub may coalesce pending jobs; this is a
  latest-main test environment, not a queue guaranteeing a deploy for every SHA.

### Required pull-request checks

The pull-request workflow is named **Pull request checks** and exposes these
stable job checks:

- `Python unit tests`
- `Container startup and authentication`

Both jobs must be configured as required status checks for the `main` branch.
In **Settings → Branches → Branch protection rules** (or the ruleset covering
`main`), enable the pull-request requirement and select both checks by their
exact names. Require branches to be up to date before merging if the repository
policy needs the checks to run against the merge result. Do not select the
post-merge deployment workflow as a PR merge gate: deployment is intentionally
separate from validation.

To verify the setting, open a test PR and confirm both checks appear and must
pass before the merge button is enabled. The repository API endpoint
`GET /repos/Yb1ku/raspberry_mcp/branches/main/protection` can also be used by
an authenticated owner; a successful response should list both contexts under
`required_status_checks.contexts`.

## Pi layout

- Source checkout: `<PROJECT_DIR>`.
- Containers: `<DEV_CONTAINER>` and `<PROD_CONTAINER>`, with host ports
  `<DEV_PORT>` and `<PROD_PORT>`. Both use port 8000 internally.
- Private runtime configuration: `<CONFIG_DIR>/dev.env` and `prod.env`, owned
  by the deployment account, mode 0600. Existing tokens are reused.
- Current/previous versions: `<STATE_DIR>/dev.json` and `prod.json`. The
  append-only `history.jsonl` records successful deployments.
- A filesystem lock serializes local deployments as well as workflow deployments.

The image contains the Docker CLI and connects to the Pi's Docker socket.
The host root, including existing submounts, is mounted read-only at
`/host`. CPU/RAM and mount identity are read from host procfs, disk usage from
the host mounts, and temperatures from host sysfs. This requires Linux 5.12+
and a Docker release supporting recursive read-only mounts (the Pi satisfies
both). The mount uses slave propagation because Docker requires it when binding
the filesystem containing its data directory. Existing submounts are read-only
on the Pi's kernel; mounts attached later should be checked and the container
recreated to reapply read-only flags.

The Docker socket grants control of the Pi's containers. Use
`RASPBERRY_MCP_ALLOWED_SERVICES` to restrict lifecycle actions to the application
containers you intend to control. Both instances share the same Docker daemon.
For example, dev can target only a disposable test container. An empty action or
service variable means that lifecycle capability is disabled. Tokens are never
baked into images or workflow artifacts. The deployment rejects a missing, blank,
whitespace-containing, short, or obviously repetitive token before it contacts
Docker.

## First-time activation

The PR prepares the implementation. It does not register a runner, change
GitHub repository settings, or replace the existing systemd services.

1. Merge the PR. The build workflow can publish the first image immediately.
   Deployment jobs stay disabled until repository variable
   `RASPBERRY_MCP_DEPLOY_ENABLED` is set to the literal string `true`.
2. In repository **Settings → Actions → Runners → New self-hosted runner**,
   choose **Linux / ARM64**. Follow GitHub's generated download and registration
   commands on the Pi, in a dedicated directory such as
   `<RUNNER_DIR>` (outside the source checkout).
   Register the extra label `raspberry-mcp-deploy` and run the service as
   `<DEPLOY_USER>`:

   ```sh
   sudo ./svc.sh install <DEPLOY_USER>
   sudo ./svc.sh start
   ```

   The runner needs outbound HTTPS to GitHub/GHCR, Docker socket access, Python
   3.10+, and noninteractive sudo for `systemctl stop/disable/enable` of the two
   legacy services during the first migration. The deployment account must have
   Docker access and noninteractive sudo. Do not assign PR jobs to this runner.
   This design assumes a private repository with trusted workflow authors.
3. Confirm both `.env` files exist, have different strong random tokens and mode
   0600. Generate one with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
   Keep your existing host/port and storage settings; the container launch
   explicitly overrides the internal listener to `0.0.0.0:8000` because a
   published container port cannot reach a listener bound only to container
   localhost. Restrict the host ports with the Pi firewall or a private network;
   do not expose plain HTTP to an untrusted network. Clients continue using
   `<DEV_ENDPOINT>/mcp` and `<PROD_ENDPOINT>/mcp`.
4. Confirm the GHCR package inherits repository access, or grant this repository
   Actions access to the package. Workflows use short-lived `GITHUB_TOKEN`
   credentials; no AWS credentials, PAT or SSH deployment secret is needed.
5. Set `RASPBERRY_MCP_DEPLOY_ENABLED=true` under **Settings → Secrets and
   variables → Actions → Variables**, then manually run **Build image and
   deploy dev** from `main` to bootstrap dev.
6. Test dev's tools and inspect the successful deployment's digest. Then run
   **Promote image to production** from `main`, supplying that full image digest.

## Token rotation and recovery

Tokens are loaded only from the mode-0600 environment file passed to Docker;
they are not in the image, deployment state, workflow artifacts, or server
responses. To rotate one environment, generate a new token in its private env
file, keep the file mode at 0600, and restart/redeploy that environment. Update
the MCP client environment at the same time. The old token stops working as
soon as the new container starts. If a token is lost, replace it with a newly
generated token rather than attempting to recover it from logs or images; the
server intentionally does not print or return token values.

For the first migration of each environment, the deployment script starts a
candidate without exposing a host port and runs an authenticated MCP
`initialize` + `health_check`. Only after that passes does it stop the matching
systemd service, start the container on its official port, and repeat the check.
The systemd unit is disabled only after success. If the new container fails,
the previous container or legacy systemd service is restored. There is a brief
interruption while switching the official port. Checkout directories are retained.

## Find the running version and choose a promotion

Open the repository's **Deployments** view and select **development** or
**production**. Each deployment records the actual source commit, exact image
digest, outcome and workflow log URL. Records are created explicitly so a
promotion of an older image is attributed to its actual source commit, not the
newer commit containing the workflow. These records do not implement approval
gates through GitHub Environments; promotion itself is an explicit manual run.

The build summary lists the published digest. A successful deployment summary
lists the active image and previous image. Packages → `raspberry_mcp` retains
the published images; this implementation has no automated registry deletion.
Keep images referenced by deployments if you introduce retention policies later.

On the deployment host, using a checkout containing these scripts:

```sh
python3 scripts/deployment_status.py
docker ps --filter name=<MCP_CONTAINER_PREFIX> --format '{{.Names}} {{.Status}} {{.Image}}'
```

The MCP tool `get_server_version` reports the source revision and environment.
The status script checks the actual container as well as the saved state.

To roll back deliberately, run the same promotion workflow with an older
successfully tested digest. It becomes a new production deployment in the
history. Rollback never moves a mutable `latest` tag or edits the source checkout.

An abrupt power loss or SIGKILL during switching can leave `*-candidate` or
`*-previous` containers behind. The next deployment refuses to overwrite them:
inspect the containers and saved state, restore the previous service if needed,
and remove only the confirmed obsolete deployment container before retrying.
