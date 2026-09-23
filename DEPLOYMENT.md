# Deployment guide

This guide describes the public deployment contract. Keep site specific topology, addresses, account names, channel IDs, and recovery procedures in a private infrastructure repository.

## Boundary

A bot deployment updates the watcher or Discord worker only. It must not restart or reconfigure the game server. Any game server change should follow its own maintenance, save, backup, rollback, and acceptance procedure.

## Secrets

Create separate high entropy values for:

* Discord bot authentication
* Watcher control requests
* Server report requests
* Anti cheat reports

Mount each credential as a read only secret file. Never place credential values in environment variables, compose files, command history, container labels, or source control.

## Watcher

Run `status_monitor.py run` with a persistent state directory and explicit bind settings. Restrict the listener to trusted game and worker networks. Use `RAGNAVIK_PROBE_MODE=hooks` when the game reports readiness directly. Use `swarm` only when the watcher has intentionally scoped Docker access.

For a system service installation, review `ragnavik-status.service` and `scripts/install-manager.sh` before use. The example creates a dedicated unprivileged account and binds to loopback unless an operator supplies another address.

## Worker

Configure all routing values through the environment and mount all credentials through secret files. Persist the worker state directory with ownership for container user `10001`. Limit the anti cheat intake to trusted server networks.

Release tags publish `ghcr.io/lostkode/ragnavik-status-bot:<version>`. Pin an exact version in the deployment manifest. Avoid floating tags for production services.

## Verification

After deployment:

1. Confirm the watcher and worker use the intended image digest.
2. Confirm both tasks remain healthy after the update window.
3. Verify unauthorized watcher requests return `403`.
4. Submit one controlled authenticated report and confirm it is accepted once.
5. Confirm the Discord command sync succeeds and the durable queue drains.
6. Confirm persistent state is mounted and writable.
7. Confirm no game service task was replaced during the bot deployment.

Use unit tests and controlled API fixtures for outage paths. Do not interrupt a live game merely to test alerts.
