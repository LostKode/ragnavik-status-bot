# Ragnavik status and Discord commands

Uptime Kuma and this read-only Swarm watcher run on Phoenix, the manager. The Discord bot runs as one Swarm task on Quetzalcoatl, a worker separate from Valheim's fenrir host. Placement uses Swarm's node hostname, so the stale LAN DNS record for Quetzalcoatl does not affect scheduling. The bot uses Discord's Gateway for slash commands and the REST API for state-change messages; the supplied application public key is not needed because there is no HTTP interactions endpoint.

The watcher samples the Valheim task and fenrir node every 30 seconds. The Valheim image's listening hook reports the current container ID when the game opens its UDP listener. Its process-exit hook clears that ready state after an internal restart. A failed task or node gets a three minute grace period. An internal game restart gets ten minutes. Planned maintenance suppresses both until its window expires. Phoenix writes maintenance, unexpected outage, and live transitions to `/var/lib/ragnavik-status/events.jsonl` and queues one log-channel message per transition. Unexpected outages also queue a DM to Daniel. The worker bot polls this queue, delivers messages with Discord's enforced nonce, and acknowledges them. If the bot is temporarily down, the queue persists.

The log channel is `1245520097758674964`, already used for anti-cheat. Daniel's DM recipient ID is `208311542016376833`. The old webhook returns 403 and is unused.

Phoenix now mounts the existing Uptime Kuma NFS export `192.168.86.20:/mnt/Alexander/uptime-kuma` at `/mnt/nfs/uptime-kuma` with the same automount options used by its other NFS shares. The infrastructure repository’s `uptime-kuma.yml` pins the service to Phoenix and keeps `/mnt/nfs/uptime-kuma/data` as its database path. Reprovisioning Phoenix must retain this mount before the stack is deployed. Its existing Quetzalcoatl ping monitor still targets a stale LAN DNS address `.26`; Swarm reports the live worker at `192.168.86.23`. Correct that monitor target separately to avoid false ping outages.

## Discord application

Use Discord application ID `1549316665131536414`. [Invite its bot](https://discord.com/oauth2/authorize?client_id=1549316665131536414&scope=bot%20applications.commands&permissions=2048) with `bot` and `applications.commands` scopes, then grant `Send Messages` in the anti-cheat log channel. Daniel and the bot must share the guild, and Daniel's guild DM setting must allow the bot to open a private channel.

The application ID and public key are public identifiers. The bot token is a credential and has not been supplied. Keep it out of Git and shell history. Once created in the Developer Portal, install it as the Swarm secret `ragnavik_discord_bot_token`. The worker bot stack mounts that secret only into the bot task. A bot token does not belong on Phoenix.

## Phoenix watcher

Install `status_monitor.py` at `/opt/ragnavik-status/status_monitor.py` and `ragnavik-status.service` at `/etc/systemd/system/ragnavik-status.service`. Store a random hook token at `/etc/ragnavik-status/hook-token` and a separate random control token at `/etc/ragnavik-status/control-token`, both owned by `klastic` with mode 0600. Create Swarm secrets `ragnavik_status_hook_token` and `ragnavik_bot_control_token` from those respective files. The hook token is used by Valheim; the control token is used by the worker bot. Bind port 8787 to Phoenix's LAN address `192.168.86.21`, allow fenrir and Quetzalcoatl to reach it, and keep it closed to the internet.

Create `/etc/ragnavik-status/status.env` with nonsecret settings:

```
RAGNAVIK_STATUS_DIR=/var/lib/ragnavik-status
RAGNAVIK_HOOK_BIND=192.168.86.21
RAGNAVIK_HOOK_TOKEN_FILE=/etc/ragnavik-status/hook-token
RAGNAVIK_CONTROL_TOKEN_FILE=/etc/ragnavik-status/control-token
```

Start the watcher only after both local token files exist. It stays quiet when first installed against an already running game until the first listening hook arrives.

## Boss progress

`progress-plugin/RagnavikProgress.cs` is a small server-only BepInEx reader. It reads Valheim's current `ZoneSystem.m_globalKeys` and reports keys beginning with `defeated_` to Phoenix only when the set changes, plus an hourly resync. The compiled `RagnavikProgress.dll` was built against the local Valheim 1.0 client assemblies. Upload it to Phoenix and create the external Docker config `ragnavik_progress_plugin_v1`; the Valheim stack mounts it under `/config/bepinex/plugins` for the image's plugin sync. Validate that the DLL loads on the live dedicated server after deployment and remove any stale runtime copy when updating it.

`/ragnavik bosses` maps the seven standard boss defeat keys to names and lists any other `defeated_` keys without guessing their meaning. These are world progression flags: the command shows whether each boss has been defeated at least once in this world. It does not count kills or identify which player made a kill.

## Worker bot

Build `Dockerfile` for linux/amd64 and publish it as `ghcr.io/lostkode/ragnavik-status-bot:1.0.0`. After installing the bot and control Swarm secrets, deploy `ragnavik-bot.yml` from LostKode/docker-swarm-configs. Its one task is pinned to Quetzalcoatl. The bot connects outward to Discord and asks Phoenix's authenticated LAN endpoint for status and queued messages.

The bot syncs these slash commands:

- `/ragnavik latest`: stable Thunderstore page for the newest published modpack.
- `/ragnavik status`: live, maintenance, offline, or initializing.
- `/ragnavik bosses`: bosses defeated in the current world.
- `/ragnavik guide`: Ragnavik getting started site.
- `/ragnavik recent`: last five status log entries, owner only.
- `/ragnavik maintenance_start`: announce a planned window, owner only.
- `/ragnavik maintenance_end`: end the window and wait for live readiness, owner only.

Commands are ephemeral replies, so using them does not fill the anti-cheat log channel. The owner-only commands verify Discord user ID `208311542016376833` in the worker bot before calling Phoenix.

## Maintenance and deployment

Before a long change, run `/ragnavik maintenance_start` in Discord or `python3 /opt/ragnavik-status/status_monitor.py maintenance start "UI and modpack update" --hours 6` on Phoenix. This queues one maintenance notice. Repeated restarts during the window do not queue more. When done, run `/ragnavik maintenance_end` or the matching Phoenix CLI command. The monitor gives Valheim 15 minutes to report ready, then posts one live notice. If the window expires, it reports an outage and sends the owner DM.

Deploy the Valheim hook and boss config changes only after the watcher and secrets are ready, inside a maintenance window. The stack update restarts the Valheim service. Test the listening and process-exit hooks, boss report, Discord channel notice, and owner DM with controlled transitions. Do not generate repeated test outages against the live world.

Phoenix can detect a fenrir power cut. A power cut that also takes Phoenix and Quetzalcoatl down cannot be reported by any service inside this site. That case needs an externally hosted heartbeat monitor.
