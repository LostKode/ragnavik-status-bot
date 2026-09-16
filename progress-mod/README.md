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

The receiving service decides where and how announcements are delivered. This package does not contain a Discord webhook, server address, token, channel ID, or Ragnavik infrastructure detail.

## Configuration

After the first server start, edit `BepInEx/config/lostkode.ragnavik.progress.cfg` on the server. Set `Enabled`, `Endpoint`, and optionally `TokenFile` and `TokenHeader`. Boss announcements and EpicMMO level announcements have independent switches. The level interval and nearby participant radius are configurable. Keep credentials in a server-only secret file rather than the package or configuration file.

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
