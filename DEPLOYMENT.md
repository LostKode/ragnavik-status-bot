# Deployment notes

The bot source is private. The separate Swarm integration lives in [LostKode/docker-swarm-configs](https://github.com/LostKode/docker-swarm-configs/pull/43). Keep secrets out of either repository.

## Deployment boundary

A status-bot deployment may update the Phoenix manager watcher, its systemd unit, or the Quetzalcoatl worker image and service. It must not copy, replace, remove, or reconfigure live Valheim mods, and it must not restart or redeploy the game server.

Changes to the game service or its mods require a separate, explicitly authorized server deployment. Before that separate deployment replaces or restarts the Valheim task, save the world and create and verify an independent rollback backup. The Ragnavik Progress mod is maintained in [LostKode/ragnavik-progress](https://github.com/LostKode/ragnavik-progress), not in this repository.

## Phoenix manager

Copy `status_monitor.py`, `ragnavik-status.service`, and `scripts/install-manager.sh` to Phoenix as `/tmp/ragnavik-status_monitor.py`, `/tmp/ragnavik-status.service`, and `/tmp/ragnavik-install-manager.sh`. Run `sudo bash /tmp/ragnavik-install-manager.sh`. The script makes independent hook and control token files and Swarm secrets, installs the read-only watcher, and starts it. It does not change the Valheim service. Verify `systemctl is-active ragnavik-status.service`, and check that `/var/lib/ragnavik-status/state.json` has an empty `pending` array at first installation.

## Worker image

GitHub Actions publishes `ghcr.io/lostkode/ragnavik-status-bot:1.0.0` from the `v1.0.0` tag. The image remains private. The local Docker build uses the same source and tag. Quetzalcoatl accepts `klastic@192.168.86.23` with `/home/klastic/.ssh/codex-quaz`. Load the local image with `docker save ghcr.io/lostkode/ragnavik-status-bot:1.0.0 | ssh -i /home/klastic/.ssh/codex-quaz klastic@192.168.86.23 docker load`, then deploy `ragnavik-bot.yml` from Phoenix with `docker stack deploy --resolve-image never`. The worker must retain the local image when the service is rescheduled or the worker is reprovisioned.

The Swarm secret `ragnavik_discord_bot_token` is already present. The watcher installer creates `ragnavik_bot_control_token` and `ragnavik_status_hook_token`. Grant the Discord application permission to send in announcements channel `1245510337139052575`; keep channel `1245520097758674964` for anti-cheat and diagnostics. The invite link is in the main README.

For automatic client-pack announcements, deploy the watcher update and verify its persistent state records the currently published client version before uploading a newer client package. The watcher polls Thunderstore every 30 minutes and waits for the matching changelog row in the public package README. It does not announce a version merely because the bot or watcher restarted.

## Verification

After a manager update, verify `systemctl is-active ragnavik-status.service`, inspect the watcher log, and confirm the authenticated status endpoint responds from its intended LAN clients. After a worker update, verify the Swarm task is healthy, the Discord command sync succeeds, and the delivery queue drains. Confirm the Valheim task was not replaced or restarted as part of either bot deployment.

Do not test outage or recovery announcements by disrupting the live game. Use unit tests and controlled API fixtures. If a separately authorized server deployment also changes hooks or the progress reporter, follow the server runbook and verify the watcher returns to `live` only after that deployment is complete.
