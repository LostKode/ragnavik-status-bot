# Ragnavik Progress

Ragnavik Progress is a server-only Valheim milestone reporter. It sends authenticated progress snapshots to an HTTP endpoint that can publish community messages through Discord or another service.

## Features

* Reports newly defeated world bosses.
* Reports connected characters reaching configurable EpicMMO level intervals.
* Uses each character's current in-game name in the report.
* Uses a private stable identifier only for duplicate prevention.
* Establishes a quiet baseline so installation does not announce old progress.
* Defaults to disabled with no endpoint or credentials.

The receiving service decides where and how announcements are delivered. This package does not contain a Discord webhook, server address, token, channel ID, or Ragnavik infrastructure detail.

## Configuration

After the first server start, edit `BepInEx/config/lostkode.ragnavik.progress.cfg` on the server. Set `Enabled`, `Endpoint`, and optionally `TokenFile` and `TokenHeader`. Boss announcements and EpicMMO level announcements have independent switches. The level interval and nearby participant radius are configurable. Keep credentials in a server-only secret file rather than the package or configuration file.

The default EpicMMO milestone interval is 10 levels. EpicMMO is optional; boss reporting still works when it is not installed.

## Endpoint payload

The endpoint receives JSON containing `server`, `instance`, `bosses`, `players`, and `milestoneStep`. Each player contains an internal `id`, current in-game `name`, and EpicMMO `level`. Return HTTP 204 after accepting the snapshot.
