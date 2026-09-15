# Deployment notes

The bot source is private. The separate Swarm integration lives in [LostKode/docker-swarm-configs](https://github.com/LostKode/docker-swarm-configs/pull/43). Keep secrets out of either repository.

## Phoenix manager

Copy `status_monitor.py`, `ragnavik-status.service`, and `scripts/install-manager.sh` to Phoenix as `/tmp/ragnavik-status_monitor.py`, `/tmp/ragnavik-status.service`, and `/tmp/ragnavik-install-manager.sh`. Run `sudo bash /tmp/ragnavik-install-manager.sh`. The script makes independent hook and control token files and Swarm secrets, installs the read-only watcher, and starts it. It does not change the Valheim service. Verify `systemctl is-active ragnavik-status.service`, and check that `/var/lib/ragnavik-status/state.json` has an empty `pending` array at first installation.

## Worker image

GitHub Actions publishes `ghcr.io/lostkode/ragnavik-status-bot:1.0.0` from the `v1.0.0` tag. The image remains private. The local Docker build uses the same source and tag. Load that image directly on Quetzalcoatl using its authorized SSH route, then deploy `ragnavik-bot.yml` from Phoenix with `docker stack deploy --resolve-image never`. The worker must retain the local image when the service is rescheduled or the worker is reprovisioned.

The Swarm secret `ragnavik_discord_bot_token` is already present. The watcher installer creates `ragnavik_bot_control_token` and `ragnavik_status_hook_token`. Grant the Discord application permission to send in channel `1245520097758674964`; the invite link is in the main README.

## Valheim hooks

Start a six hour maintenance window before applying the Valheim stack change because it restarts the service. Create the Docker config `ragnavik_progress_plugin_v1` from the repository's `RagnavikProgress.dll` on Phoenix. Then deploy the changed `valheim-1.0.yml`, check the game listening hook and boss reader load, and end maintenance after the server is ready. Validate one log channel transition and one owner DM with a controlled outage; avoid repeating live test outages.
