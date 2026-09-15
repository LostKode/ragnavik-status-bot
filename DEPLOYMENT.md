# Deployment notes

The bot source is private. The separate Swarm integration lives in [LostKode/docker-swarm-configs](https://github.com/LostKode/docker-swarm-configs/pull/43). Keep secrets out of either repository.

## Phoenix manager

Copy `status_monitor.py`, `ragnavik-status.service`, and `scripts/install-manager.sh` to Phoenix as `/tmp/ragnavik-status_monitor.py`, `/tmp/ragnavik-status.service`, and `/tmp/ragnavik-install-manager.sh`. Run `sudo bash /tmp/ragnavik-install-manager.sh`. The script makes independent hook and control token files and Swarm secrets, installs the read-only watcher, and starts it. It does not change the Valheim service. Verify `systemctl is-active ragnavik-status.service`, and check that `/var/lib/ragnavik-status/state.json` has an empty `pending` array at first installation.

## Worker image

GitHub Actions publishes `ghcr.io/lostkode/ragnavik-status-bot:1.0.0` from the `v1.0.0` tag. The image remains private. The local Docker build uses the same source and tag. Quetzalcoatl accepts `klastic@192.168.86.23` with `/home/klastic/.ssh/codex-quaz`. Load the local image with `docker save ghcr.io/lostkode/ragnavik-status-bot:1.0.0 | ssh -i /home/klastic/.ssh/codex-quaz klastic@192.168.86.23 docker load`, then deploy `ragnavik-bot.yml` from Phoenix with `docker stack deploy --resolve-image never`. The worker must retain the local image when the service is rescheduled or the worker is reprovisioned.

The Swarm secret `ragnavik_discord_bot_token` is already present. The watcher installer creates `ragnavik_bot_control_token` and `ragnavik_status_hook_token`. Grant the Discord application permission to send in announcements channel `1245510337139052575`; keep channel `1245520097758674964` for anti-cheat and diagnostics. The invite link is in the main README.

For automatic client-pack announcements, deploy the watcher update and verify its persistent state records the currently published client version before uploading a newer client package. The watcher polls Thunderstore every 30 minutes and waits for the matching changelog row in the public package README. It does not announce a version merely because the bot or watcher restarted.

## Valheim hooks

Start a six hour maintenance window before applying the Valheim stack change because it restarts the service. The watcher keeps that window active through multiple planned restarts. Create the Docker config `ragnavik_progress_plugin_v2` from the repository's corrected `RagnavikProgress.dll` on Phoenix. Mount the anti cheat client allowlist config at the runtime BepInEx path, not just the staging config path. Then deploy the changed `valheim-1.0.yml` once, check the game listening hook, all 15 anti cheat allowlist entries, and `Ragnavik Progress 1.0.1` loading. The manager's `/bosses` report should update after Valheim is ready. End maintenance with `/ragnavik maintenance_end` or the Phoenix CLI command after the final update, then confirm the watcher returns to `live` and the Discord delivery queue empties. An owner DM can be tested directly through the bot without causing a live server outage.
