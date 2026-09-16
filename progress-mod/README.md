# Ragnavik Progress

Ragnavik Progress is a server-only Valheim milestone reporter. It sends authenticated progress snapshots to an HTTP endpoint that can publish community messages through Discord or another service.

## Features

* Reports newly defeated world bosses.
* Records the killing player and nearby participants for future boss defeats.
* Reports connected characters reaching configurable EpicMMO level intervals.
* Uses each character's current in-game name in the report.
* Uses a private stable identifier only for duplicate prevention.
* Establishes a quiet baseline so installation does not announce old progress.
* Defaults to disabled with no endpoint or credentials.
* Does not report ordinary creature kills.

## What server administrators need

This mod is the game-side reporter. It does not bundle or require the Ragnavik Discord bot. A server administrator must provide an HTTP receiver that:

1. Is reachable from the dedicated Valheim server.
2. Accepts authenticated JSON `POST` requests at the configured endpoint.
3. Stores enough state to prevent duplicate announcements across restarts.
4. Routes accepted events to Discord, another chat service, a database, or logs.
5. Returns HTTP `204 No Content` after safely accepting a report.

The receiver can run in Docker, as a system service, as a serverless endpoint, or inside an existing community bot. Docker is optional. If Discord is used, the administrator supplies their own bot application or webhook bridge and their own channel IDs.

## Configuration

After the first server start, edit `BepInEx/config/lostkode.ragnavik.progress.cfg` on the server. Set `Enabled`, `Endpoint`, and optionally `TokenFile` and `TokenHeader`. Boss announcements and EpicMMO level announcements have independent switches. The level interval and nearby participant radius are configurable.

The default EpicMMO milestone interval is 10 levels. EpicMMO is optional; boss reporting still works when it is not installed.

| Setting | Default | Purpose |
| --- | --- | --- |
| `Enabled` | `false` | Master switch for all reporting. |
| `ReportBossDefeats` | `true` | Enables boss defeat snapshots and attribution. |
| `ReportEpicMMOLevels` | `true` | Enables EpicMMO level snapshots. |
| `EpicMMOLevelStep` | `10` | Level interval used by the receiving service. |
| `BossParticipantRadius` | `100` | Distance in meters used to identify nearby participants. |
| `Endpoint` | blank | Private receiving endpoint. |
| `TokenFile` | blank | Server-only authentication token file. |
| `TokenHeader` | `X-Progress-Token` | Authentication header name. |
| `ServerName` | `Valheim` | Server name included in reports. |
| `CheckSeconds` | `30` | Progress polling interval. |
| `HeartbeatSeconds` | `3600` | Unchanged-state resynchronization interval. |

## Endpoint payload

The endpoint receives JSON containing `server`, `instance`, `bosses`, `bossKills`, `players`, and `milestoneStep`. Each player contains an internal `id`, current in-game `name`, and EpicMMO `level`. Each boss kill contains an event ID, world key, boss name, killing player, and nearby participant names. Return HTTP 204 after accepting the snapshot.

Example request body:

```json
{
  "server": "Example Server",
  "instance": "dedicated-server-1",
  "bosses": ["defeated_eikthyr"],
  "bossKills": [
    {
      "id": "boss-event-id",
      "key": "defeated_eikthyr",
      "boss": "Eikthyr",
      "killer": "Astrid",
      "participants": ["Astrid", "Bjorn"]
    }
  ],
  "players": [
    {
      "id": "private-character-id",
      "name": "Astrid",
      "level": 20
    }
  ],
  "milestoneStep": 10
}
```

When `TokenFile` contains a token, the mod sends its contents in the header named by `TokenHeader`. The receiver should compare that value securely, reject invalid requests, validate body sizes and fields, and avoid printing tokens or private identifiers in public messages.

Reports are snapshots and may be repeated during heartbeat synchronization. The receiver is responsible for announcing only new boss event IDs, newly added boss keys, and newly crossed player-level thresholds. Character IDs are for private duplicate tracking; use the accompanying in-game `name` in community messages.
