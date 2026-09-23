# Ragnavik Status Bot

Ragnavik Status Bot provides authenticated Valheim status monitoring, Discord commands, maintenance notices, progression summaries, and anti cheat event delivery.

The container image contains application code only. Deployment specific addresses, Discord identifiers, and credentials are supplied at runtime. Credentials must be mounted as Docker secrets or equivalent read only files.

## Features

* Persistent status, maintenance, and recovery tracking
* Authenticated readiness, progression, and anti cheat endpoints
* Discord slash commands for server status, player records, world state, log submission help, and maintenance
* Deduplicated boss, level, and death milestones
* Quiet client pack release monitoring
* Durable event queues that survive bot restarts

The server progress reporter and anti cheat reporter are maintained separately. This repository receives their authenticated reports but does not package either server mod.

## Configuration

The worker container expects these deployment values:

| Variable | Purpose |
| --- | --- |
| `RAGNAVIK_STATUS_URL` | Base URL for the authenticated watcher API |
| `DISCORD_LOG_CHANNEL_ID` | Administrative and anti cheat destination |
| `DISCORD_ANNOUNCEMENTS_CHANNEL_ID` | Player facing status destination |
| `DISCORD_LONGHOUSE_CHANNEL_ID` | Progression milestone destination |
| `DISCORD_OWNER_ID` | User permitted to run owner only commands and receive outage messages |
| `DISCORD_BOT_TOKEN_FILE` | Mounted Discord token file |
| `RAGNAVIK_CONTROL_TOKEN_FILE` | Mounted watcher control token file |
| `RAGNAVIK_ANTICHEAT_BIND` | Anti cheat intake bind address |
| `RAGNAVIK_ANTICHEAT_PORT` | Anti cheat intake port |
| `RAGNAVIK_ANTICHEAT_TOKEN_FILE` | Mounted anti cheat token file |
| `RAGNAVIK_BOT_STATE_DIR` | Persistent worker state directory |

The watcher accepts these values:

| Variable | Purpose |
| --- | --- |
| `RAGNAVIK_STATUS_DIR` | Persistent watcher state directory |
| `RAGNAVIK_HOOK_BIND` | Listener bind address |
| `RAGNAVIK_HOOK_TOKEN_FILE` | Mounted report token file |
| `RAGNAVIK_CONTROL_TOKEN_FILE` | Mounted control token file |
| `RAGNAVIK_PROBE_MODE` | `hooks` for reported readiness or `swarm` for Docker inspection |
| `RAGNAVIK_SERVICE` | Game service name when using Swarm inspection |
| `RAGNAVIK_NODE` | Game node name when using Swarm inspection |

Keep the watcher endpoint on a trusted network. Do not expose it directly to the internet.

## Discord commands

The bot provides status, bosses, deaths, statistics, levels, records, milestones, world state, log submission guidance, recent events, and maintenance commands under `/ragnavik`. Players can use `/ragnavik logs` for a short issue report checklist and a link to the full website guide. Administrative commands check `DISCORD_OWNER_ID` and use ephemeral replies.

## Security model

The Discord token, watcher control token, report token, and anti cheat token are never built into the image. The published image uses environment variables only for nonsecret routing values and mounted files for secrets. Authentication comparisons use constant time checks. Discord messages disable automatic mention parsing.

Persistent state can contain player names and operational history. Keep state volumes private and exclude them from images, source control, and backups intended for public distribution.

## Development

Run the test suite with:

```console
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v
```

Create a version tag to publish the Linux AMD64 image through GitHub Actions. See [DEPLOYMENT.md](DEPLOYMENT.md) for a generic deployment checklist.
