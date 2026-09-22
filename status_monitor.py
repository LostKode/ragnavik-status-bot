#!/usr/bin/env python3
"""Low-noise Ragnavik status and maintenance monitor."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import http.server
import json
import os
import re
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

STATE_DIR = Path(os.environ.get("RAGNAVIK_STATUS_DIR", "/var/lib/ragnavik-status"))
STATE_FILE = STATE_DIR / "state.json"
LOCK_FILE = STATE_DIR / "state.lock"
EVENT_FILE = STATE_DIR / "events.jsonl"
PROBE_MODE = os.environ.get("RAGNAVIK_PROBE_MODE", "swarm")
SERVICE = os.environ.get("RAGNAVIK_SERVICE", "ragnavik_valheim")
NODE = os.environ.get("RAGNAVIK_NODE", "fenrir")
HOOK_TOKEN_FILE = os.environ.get("RAGNAVIK_HOOK_TOKEN_FILE", "/etc/ragnavik-status/hook-token")
CONTROL_TOKEN_FILE = os.environ.get("RAGNAVIK_CONTROL_TOKEN_FILE", "/etc/ragnavik-status/control-token")
DOWN_GRACE = int(os.environ.get("RAGNAVIK_DOWN_GRACE_SECONDS", "180"))
RESTART_GRACE = int(os.environ.get("RAGNAVIK_RESTART_GRACE_SECONDS", "600"))
POLL_SECONDS = int(os.environ.get("RAGNAVIK_POLL_SECONDS", "30"))
CLIENT_PACK_CHECK_SECONDS = int(os.environ.get("RAGNAVIK_CLIENT_PACK_CHECK_SECONDS", "1800"))
CLIENT_PACK_API = "https://ragnavik.vercel.app/api/changelog"
CLIENT_PACK_PAGE = "https://valheim.hexium.gg/mods/LostKode/Ragnavik"

BOSS_NAMES = {
    "defeated_eikthyr": "Eikthyr",
    "defeated_gdking": "The Elder",
    "defeated_bonemass": "Bonemass",
    "defeated_dragon": "Moder",
    "defeated_goblinking": "Yagluth",
    "defeated_queen": "The Queen",
    "defeated_fader": "Fader",
    "defeated_frozenking": "Kall Fimbulbringer",
}


MAX_PROGRESS_BODY = 262144

def now():
    return time.time()


def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def locked_state():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
            state.setdefault("phase", "unknown")
            state.setdefault("pending", [])
            original = json.dumps(state, sort_keys=True)
            yield state
            if not STATE_FILE.exists() or json.dumps(state, sort_keys=True) != original:
                temporary = STATE_FILE.with_suffix(".tmp")
                temporary.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")
                temporary.replace(STATE_FILE)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def record(state, kind, reason, destinations):
    timestamp = now()
    event_id = hashlib.sha256(f"{timestamp}:{kind}:{reason}".encode()).hexdigest()[:20]
    event = {"id": event_id, "at": utc(timestamp), "kind": kind, "reason": reason}
    with EVENT_FILE.open("a") as log:
        log.write(json.dumps(event, sort_keys=True) + "\n")
        log.flush()
        os.fsync(log.fileno())
    for destination, message in destinations:
        state["pending"].append({"id": event_id + destination, "destination": destination,
                                 "message": message, "nonce": event_id + destination[:4]})


def docker(*args):
    result = subprocess.run(["docker", *args], text=True, capture_output=True, timeout=12)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"docker {' '.join(args)} failed")
    return result.stdout.strip()
    if PROBE_MODE == "hooks":
        with locked_state() as state:
            container = state.get("ready_container", "")
            ready_at = state.get("ready_at", "")
            stopped_at = state.get("stopped_at", "")
        healthy = bool(container and (not stopped_at or ready_at > stopped_at))
        return {"healthy": healthy,
                "reason": "game listener has not reported ready" if not healthy else "ready",
                "task": "", "container": container}




def probe():
    if PROBE_MODE == "hooks":
        with locked_state() as state:
            container = state.get("ready_container", "")
            ready_at = state.get("ready_at", "")
            stopped_at = state.get("stopped_at", "")
        healthy = bool(container and (not stopped_at or ready_at > stopped_at))
        return {"healthy": healthy,
                "reason": "game listener has not reported ready" if not healthy else "ready",
                "task": "", "container": container}
    try:
        node_state = docker("node", "inspect", NODE, "--format", "{{.Status.State}}")
        lines = docker("service", "ps", SERVICE, "--filter", "desired-state=running",
                       "--format", "{{json .}}").splitlines()
        tasks = [json.loads(line) for line in lines if line]
        current = next((task for task in tasks if task.get("Node") == NODE and
                        task.get("DesiredState") == "Running"), None)
        if not current:
            return {"healthy": False, "reason": "no running Swarm task", "task": ""}
        task_id = current["ID"]
        status = json.loads(docker("inspect", task_id, "--format", "{{json .Status}}"))
        container = status.get("ContainerStatus", {}).get("ContainerID", "")
        running = node_state == "ready" and status.get("State") == "running"
        reason = ("Valheim host is down" if node_state != "ready" else
                  f"task is {status.get('State', 'unknown')}")
        return {"healthy": running, "reason": reason, "task": task_id,
                "container": container}
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        return {"healthy": False, "reason": f"Swarm status unavailable: {exc}", "task": ""}


def public_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "RagnavikStatus/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def latest_client_pack(payload):
    entries = payload.get("entries")
    if payload.get("schemaVersion") != 1 or not isinstance(entries, list) or not entries:
        raise ValueError("invalid Ragnavik changelog response")
    entry = entries[0]
    version = entry.get("version")
    title = entry.get("title")
    changes = entry.get("changes")
    if (not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or not isinstance(title, str) or not title.strip()
            or not isinstance(changes, list) or not changes
            or not all(isinstance(change, str) and change.strip() for change in changes)):
        raise ValueError("latest Ragnavik changelog entry is incomplete")
    notes = "\n".join(f"• {change.strip()[:850]}" for change in changes[:4])[:1200]
    return {"version": version, "title": title.strip(), "notes": notes,
            "published_at": entry.get("publishedAt", "")}


def version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def client_pack_message(version, title, notes):
    return (f"**Ragnavik client pack v{version} is live**\n\n"
            f"**{title}**\n{notes}\n\n"
            f"[Get the latest client pack on Hexium]({CLIENT_PACK_PAGE})")


def recovery_message(state):
    version = state.get("client_pack_version")
    title = state.get("client_pack_title")
    notes = state.get("client_pack_notes")
    if version and title and notes:
        return ("**Ragnavik is live again**\n\n"
                f"Latest client pack: **v{version}**\n"
                f"**{title}**\n{notes}\n\n"
                f"[Get the latest client pack on Hexium]({CLIENT_PACK_PAGE})")
    return "Ragnavik is live again. Players can connect."


def check_client_pack():
    """Queue exactly one announcement per newer published client pack version."""
    latest = latest_client_pack(public_json(CLIENT_PACK_API))
    version = latest["version"]
    with locked_state() as state:
        previous = state.get("client_pack_version")
        if previous is None:
            state["client_pack_version"] = version
            state["client_pack_published_at"] = latest["published_at"]
            state["client_pack_title"] = latest["title"]
            state["client_pack_notes"] = latest["notes"]
            return
        if previous == version:
            state["client_pack_title"] = latest["title"]
            state["client_pack_notes"] = latest["notes"]
            return
        if version_tuple(version) <= version_tuple(previous):
            return
        record(state, "client_pack_release", version,
               [("channel", client_pack_message(version, latest["title"], latest["notes"]))])
        state["client_pack_version"] = version
        state["client_pack_published_at"] = latest["published_at"]
        state["client_pack_title"] = latest["title"]
        state["client_pack_notes"] = latest["notes"]

def client_pack_loop():
    while True:
        try:
            check_client_pack()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"Ragnavik client pack check deferred: {exc}", flush=True)
        threading.Event().wait(CLIENT_PACK_CHECK_SECONDS)


def reconcile(state, observation, timestamp):
    container = observation.get("container", "")
    ready = observation["healthy"] and container and container.startswith(
        state.get("ready_container", "UNMATCHED")) and state.get("ready_container")
    maintenance = state.get("maintenance")
    if (ready and state["phase"] == "maintenance" and maintenance and
            not maintenance.get("finished") and timestamp < maintenance["until"]):
        return
    if ready:
        state.pop("down_since", None)
        if state["phase"] == "maintenance" or state.pop("outage_was_maintenance", False):
            record(state, "live", "server listening",
                   [("announcements", recovery_message(state))])
            state["phase"] = "live"
            state.pop("maintenance", None)
            state.pop("outage_reason", None)
        elif state["phase"] == "offline":
            reason = state.pop("outage_reason", "unknown operational cause")
            record(state, "live", "unexpected outage recovered",
                   [("logs", "Ragnavik recovered from an unexpected outage."),
                    ("dm", f"Ragnavik recovered from the unexpected outage. Previous cause: {reason}.")])
            state["phase"] = "live"
        elif state["phase"] == "unknown":
            state["phase"] = "live"
        return
    if state["phase"] == "unknown" and observation["healthy"]:
        # Initial installation may have missed the one-time ready hook.
        return
    maintenance = state.get("maintenance")
    if maintenance and state["phase"] == "maintenance":
        if timestamp < maintenance["until"]:
            return
        reason = "maintenance window expired before the server became live"
    else:
        reason = observation["reason"] if not observation["healthy"] else "server has not reported ready"
    state.setdefault("down_since", timestamp)
    grace = DOWN_GRACE if not observation["healthy"] else RESTART_GRACE
    if state["phase"] != "offline" and timestamp - state["down_since"] >= grace:
        state["outage_reason"] = reason
        state["outage_was_maintenance"] = bool(maintenance)
        record(state, "offline", reason,
               [("logs", "Ragnavik is offline unexpectedly. The issue is being investigated."),
                ("dm", f"Ragnavik outage alert: {reason}. I will send you one recovery update.")])
        state["phase"] = "offline"
        state.pop("maintenance", None)



class StatusHandler(http.server.BaseHTTPRequestHandler):
    def error_response(self, status, code, detail):
        data = json.dumps({"error": code, "detail": detail}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self, token_file, header):
        try:
            expected = Path(token_file).read_text().strip()
        except OSError:
            self.send_error(503)
            return False
        if not expected or not hmac.compare_digest(expected, self.headers.get(header, "")):
            self.send_error(403)
            return False
        return True

    def body(self, maximum):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= maximum:
                raise ValueError(f"body must be between 1 and {maximum} bytes")
            return self.rfile.read(size)
        except ValueError as exc:
            self.error_response(400, "invalid_body", str(exc))
            return None

    def response(self, payload):
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path not in ("/state", "/events", "/recent", "/maintenance/game"):
            self.send_error(404)
            return
        if self.path == "/maintenance/game":
            if not self.authorized(HOOK_TOKEN_FILE, "X-Ragnavik-Token"):
                return
            with locked_state() as state:
                maintenance = state.get("maintenance") or {}
                self.response({"active": state.get("phase") == "maintenance" and not maintenance.get("finished", False),
                               "shutdownAt": maintenance.get("shutdown_at"), "reason": maintenance.get("reason", "")})
            return
        if not self.authorized(CONTROL_TOKEN_FILE, "X-Ragnavik-Control"):
            return
        if self.path == "/recent":
            if EVENT_FILE.exists():
                lines = EVENT_FILE.read_text().splitlines()[-5:]
                self.response([json.loads(line) for line in lines])
            else:
                self.response([])
            return
        with locked_state() as state:
            if self.path == "/events":
                self.response(state["pending"][0] if state["pending"] else {})
            else:
                response = {key: state.get(key) for key in
                            ("phase", "maintenance", "boss_keys", "boss_at",
                             "boss_player_counts", "online_count", "latest_boss",
                             "client_pack_version", "world_day", "world_day_fraction",
                             "active_event", "milestone_history", "recent_deaths")}
                if "death_counts" in state:
                    names = state.get("player_names", {})
                    response["death_leaderboard"] = sorted(
                        ({"name": names.get(player_id, "Unknown Viking"), "deaths": deaths}
                         for player_id, deaths in state["death_counts"].items()),
                        key=lambda player: (-player["deaths"], player["name"].casefold()))
                    response["total_deaths"] = sum(state["death_counts"].values())
                if "player_levels" in state:
                    names = state.get("player_names", {})
                    response["level_leaderboard"] = sorted(
                        ({"name": names[player_id], "level": level}
                         for player_id, level in state["player_levels"].items()
                         if player_id in names),
                        key=lambda player: (-player["level"], player["name"].casefold()))
                if "player_boss_keys" in state:
                    names = state.get("player_names", {})
                    response["boss_leaderboard"] = sorted(
                        ({"name": names[player_id],
                          "bosses": len(set(keys) & set(BOSS_NAMES))}
                         for player_id, keys in state["player_boss_keys"].items()
                         if player_id in names),
                        key=lambda player: (-player["bosses"], player["name"].casefold()))
                self.response(response)

    def do_POST(self):
        hook = self.path in ("/ready", "/notready", "/bosses", "/progress")
        control = self.path in ("/ack", "/maintenance/start", "/maintenance/end")
        if not hook and not control:
            self.send_error(404)
            return
        if hook and not self.authorized(HOOK_TOKEN_FILE, "X-Ragnavik-Token"):
            return
        if control and not self.authorized(CONTROL_TOKEN_FILE, "X-Ragnavik-Control"):
            return
        if self.path == "/maintenance/end":
            try:
                maintenance_end()
            except RuntimeError as exc:
                self.send_error(409, str(exc))
                return
            self.send_response(204)
            self.end_headers()
            return
        raw = self.body(MAX_PROGRESS_BODY if self.path == "/progress" else
                        4096 if self.path == "/bosses" else 512)
        if raw is None:
            return
        if self.path in ("/ready", "/notready"):
            container = raw.decode().strip()
            if not container or not all(ch in "0123456789abcdef" for ch in container):
                self.send_error(400)
                return
            with locked_state() as state:
                if self.path == "/ready":
                    state["ready_container"] = container
                    state["ready_at"] = utc(now())
                elif state.get("ready_container", "").startswith(container):
                    state.pop("ready_container", None)
                    state["stopped_at"] = utc(now())
        elif self.path == "/bosses":
            try:
                report = json.loads(raw)
                container = report["container"]
                keys = report["keys"]
                if (not isinstance(container, str) or not container or
                        not all(ch in "0123456789abcdef" for ch in container) or
                        not isinstance(keys, list)
                        or len(keys) > 50 or not all(isinstance(key, str) and
                        len(key) <= 100 and key.startswith("defeated_") for key in keys)):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                self.send_error(400)
                return
            observation = probe()
            if not observation["healthy"] or not observation.get("container", "").startswith(container):
                self.send_error(409)
                return
            with locked_state() as state:
                state["boss_keys"] = sorted(set(keys))
                state["boss_at"] = utc(now())
        elif self.path == "/progress":
            try:
                report = json.loads(raw)
                instance = report["instance"]
                server = report["server"]
                bosses = report["bosses"]
                players = report.get("players", [])
                player_bosses = report.get("playerBosses")
                boss_kills = report.get("bossKills", [])
                deaths = report.get("deaths", [])
                world = report.get("world")
                step = report["milestoneStep"]
                if not isinstance(instance, str) or not instance:
                    raise ValueError("instance is required")
                if len(instance) > 64 or not all(ch in "0123456789abcdef" for ch in instance):
                    raise ValueError("instance must be a lowercase hexadecimal container ID")
                if not isinstance(server, str) or not 0 < len(server) <= 80:
                    raise ValueError("server must be a non-empty string of at most 80 characters")
                if (not isinstance(bosses, list) or len(bosses) > 50 or
                        not all(isinstance(key, str) and len(key) <= 100 and
                                key.startswith("defeated_") for key in bosses)):
                    raise ValueError("bosses contains an invalid global key")
                if not isinstance(players, list) or len(players) > 64:
                    raise ValueError("players must contain at most 64 entries")
                if (player_bosses is not None and
                        (not isinstance(player_bosses, list) or len(player_bosses) > 256)):
                    raise ValueError("playerBosses must contain at most 256 entries")
                if not isinstance(boss_kills, list) or len(boss_kills) > 20:
                    raise ValueError("bossKills must contain at most 20 entries")
                if not isinstance(deaths, list) or len(deaths) > 20:
                    raise ValueError("deaths must contain at most 20 entries")
                if world is not None:
                    world_day = world["day"]
                    world_fraction = world["dayFraction"]
                    active_event = world["activeEvent"]
                    if (not isinstance(world_day, int) or not 0 <= world_day <= 1000000 or
                            not isinstance(world_fraction, (int, float)) or
                            not 0 <= world_fraction <= 1 or
                            not isinstance(active_event, str) or len(active_event) > 100):
                        raise ValueError("world contains an invalid day, time, or event")
                if not isinstance(step, int) or not 1 <= step <= 100:
                    raise ValueError("milestoneStep must be an integer from 1 to 100")
                clean_players = []
                for player in players:
                    player_id = player["id"]
                    name = player["name"]
                    level = player["level"]
                    if (not isinstance(player_id, str) or not 0 < len(player_id) <= 80 or
                            not isinstance(name, str) or not 0 < len(name) <= 80 or
                            not isinstance(level, int) or not 1 <= level <= 10000):
                        raise ValueError("players contains an invalid id, name, or level")
                    clean_players.append((player_id, name, level))
                clean_player_bosses = []
                if player_bosses is not None:
                    for player in player_bosses:
                        player_id = player["id"]
                        keys = player["bosses"]
                        if (not isinstance(player_id, str) or not 0 < len(player_id) <= 80 or
                                not isinstance(keys, list) or len(keys) > 50 or
                                not all(isinstance(key, str) and len(key) <= 100 and
                                        key.startswith("defeated_") for key in keys)):
                            raise ValueError("playerBosses contains an invalid id or boss key")
                        clean_player_bosses.append((player_id, sorted(set(keys))))
                clean_boss_kills = []
                for kill in boss_kills:
                    event_id = kill["id"]
                    key = kill["key"]
                    boss = kill["boss"]
                    killer = kill["killer"]
                    participants = kill["participants"]
                    if (not isinstance(event_id, str) or not 0 < len(event_id) <= 120 or
                            not isinstance(key, str) or len(key) > 100 or
                            not isinstance(boss, str) or not 0 < len(boss) <= 100 or
                            not isinstance(killer, str) or not 0 < len(killer) <= 80 or
                            not isinstance(participants, list) or len(participants) > 64 or
                            not all(isinstance(name, str) and 0 < len(name) <= 80
                                    for name in participants)):
                        raise ValueError("bossKills contains an invalid event")
                    clean_boss_kills.append((event_id, key, boss, killer, participants))
                clean_deaths = []
                for death in deaths:
                    event_id = death["id"]
                    player_id = death["playerId"]
                    name = death["name"]
                    cause = death.get("cause", "Unknown")
                    if (not isinstance(event_id, str) or not 0 < len(event_id) <= 160 or
                            not isinstance(player_id, str) or not 0 < len(player_id) <= 80 or
                            not isinstance(name, str) or not 0 < len(name) <= 80 or
                            not isinstance(cause, str) or not 0 < len(cause) <= 120):
                        raise ValueError("deaths contains an invalid event")
                    clean_deaths.append((event_id, player_id, name, cause))
            except json.JSONDecodeError:
                self.error_response(400, "invalid_json", "request body is not valid JSON")
                return
            except KeyError as exc:
                self.error_response(400, "missing_field", f"required field is missing: {exc.args[0]}")
                return
            except (ValueError, TypeError) as exc:
                self.error_response(400, "invalid_progress", str(exc) or "progress payload is invalid")
                return
            observation = probe()
            if (not observation["healthy"] or
                    not observation.get("container", "").startswith(instance)):
                self.send_error(409)
                return
            with locked_state() as state:
                had_boss_baseline = "boss_keys" in state
                previous_bosses = set(state.get("boss_keys", []))
                current_bosses = set(bosses)
                received_kill_keys = {key for _, key, _, _, _ in clean_boss_kills if key}
                attributed_boss_keys = set(state.get("attributed_boss_keys", []))
                if had_boss_baseline:
                    for key in sorted(current_bosses - previous_bosses):
                        if key in received_kill_keys or key in attributed_boss_keys:
                            continue
                        name = BOSS_NAMES.get(key, key.removeprefix("defeated_").replace("_", " ").title())
                        state["latest_boss"] = name
                        history = state.setdefault("milestone_history", [])
                        history.append({"at": utc(now()), "message": f"{name} was defeated"})
                        state["milestone_history"] = history[-50:]
                        record(state, "boss_milestone", key,
                               [("longhouse", f"{server} milestone: {name} has been defeated!")])
                state["boss_keys"] = sorted(current_bosses)
                state["boss_at"] = utc(now())

                seen_kills = state.setdefault("boss_kill_events", [])
                seen_set = set(seen_kills)
                announced_player_bosses = set(state.get("announced_player_bosses", []))
                for event_id, key, boss, killer, participants in clean_boss_kills:
                    if event_id in seen_set:
                        continue
                    boss_name = BOSS_NAMES.get(key, boss)
                    boss_identity = key or boss_name.casefold()
                    player_boss = f"{killer.casefold()}\\0{boss_identity}"
                    if player_boss not in announced_player_bosses:
                        state["latest_boss"] = boss_name
                        history = state.setdefault("milestone_history", [])
                        history.append({"at": utc(now()),
                                        "message": f"{killer} defeated {boss_name} for the first time"})
                        state["milestone_history"] = history[-50:]
                        party = ", ".join(participants) if participants else "No nearby players recorded"
                        message = (f"{server} milestone: {killer} defeated {boss_name} "
                                   f"for the first time! Party: {party}.")
                        record(state, "boss_kill", event_id, [("longhouse", message)])
                        announced_player_bosses.add(player_boss)
                    seen_kills.append(event_id)
                    seen_set.add(event_id)
                    if key:
                        attributed_boss_keys.add(key)
                state["boss_kill_events"] = seen_kills[-500:]
                state["attributed_boss_keys"] = sorted(attributed_boss_keys)
                state["announced_player_bosses"] = sorted(announced_player_bosses)

                milestones = state.setdefault("player_milestones", {})
                names = state.setdefault("player_names", {})
                levels = state.setdefault("player_levels", {})
                for player_id, name, level in clean_players:
                    threshold = level // step * step
                    if player_id not in milestones:
                        milestones[player_id] = threshold
                        if threshold >= step and level == threshold:
                            record(state, "player_milestone", f"{player_id}:{threshold}",
                                   [("longhouse", f"{name} reached EpicMMO level {threshold}!")])
                    elif threshold > milestones[player_id]:
                        milestones[player_id] = threshold
                        record(state, "player_milestone", f"{player_id}:{threshold}",
                               [("longhouse", f"{name} reached EpicMMO level {threshold}!")])
                        history = state.setdefault("milestone_history", [])
                        history.append({"at": utc(now()),
                                        "message": f"{name} reached EpicMMO level {threshold}"})
                        state["milestone_history"] = history[-50:]
                    names[player_id] = name
                    levels[player_id] = level
                state["online_count"] = len(clean_players)
                state["players_at"] = utc(now())
                if player_bosses is not None:
                    known_player_bosses = state.setdefault("player_boss_keys", {})
                    for player_id, keys in clean_player_bosses:
                        known_player_bosses[player_id] = keys
                    counts = {}
                    for keys in known_player_bosses.values():
                        for key in set(keys):
                            counts[key] = counts.get(key, 0) + 1
                    state["boss_player_counts"] = dict(sorted(counts.items()))
                    state["player_bosses_at"] = utc(now())
                seen_deaths = state.setdefault("death_events", [])
                seen_death_ids = set(seen_deaths)
                death_counts = state.setdefault("death_counts", {})
                recent_deaths = state.setdefault("recent_deaths", [])
                for event_id, player_id, name, cause in clean_deaths:
                    if event_id in seen_death_ids:
                        continue
                    death_counts[player_id] = death_counts.get(player_id, 0) + 1
                    names[player_id] = name
                    recent_deaths.append({"at": utc(now()), "name": name, "cause": cause})
                    seen_deaths.append(event_id)
                    seen_death_ids.add(event_id)
                state["death_events"] = seen_deaths[-2000:]
                state["recent_deaths"] = recent_deaths[-50:]
                if clean_deaths:
                    state["deaths_at"] = utc(now())
                if world is not None:
                    state["world_day"] = world_day
                    state["world_day_fraction"] = world_fraction
                    state["active_event"] = active_event
                    state["world_at"] = utc(now())
        elif self.path == "/ack":
            try:
                event_id = json.loads(raw)["id"]
                if not isinstance(event_id, str):
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                self.send_error(400)
                return
            with locked_state() as state:
                state["pending"] = [item for item in state["pending"] if item["id"] != event_id]
        else:
            try:
                request = json.loads(raw)
                reason = request["reason"]
                hours = float(request.get("hours", 6))
                countdown_minutes = float(request.get("countdownMinutes", 10))
                if (not isinstance(reason, str) or not 0 < len(reason) <= 200 or
                        not 0 < hours <= 72 or not 0.5 <= countdown_minutes <= 60):
                    raise ValueError
                maintenance_start(reason, hours, countdown_minutes)
            except (ValueError, KeyError, TypeError):
                self.send_error(400)
                return
            except RuntimeError as exc:
                self.send_error(409, str(exc))
                return
        self.send_response(204)
        self.end_headers()

    def log_message(self, *_args):
        pass


def run():
    bind = os.environ.get("RAGNAVIK_HOOK_BIND", "192.168.86.21")
    server = http.server.ThreadingHTTPServer((bind, 8787), StatusHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=client_pack_loop, daemon=True).start()
    print("Ragnavik monitor listening on port 8787", flush=True)
    while True:
        observation = probe()
        with locked_state() as state:
            reconcile(state, observation, now())
        time.sleep(POLL_SECONDS)


def maintenance_start(reason, hours, countdown_minutes=10):
    with locked_state() as state:
        if state.get("maintenance") and state["phase"] == "maintenance":
            raise RuntimeError("maintenance is already active")
        started = now()
        state["maintenance"] = {"reason": reason, "until": started + hours * 3600,
                                "shutdown_at": started + countdown_minutes * 60, "finished": False}
        state["phase"] = "maintenance"
        state.pop("down_since", None)
        record(state, "maintenance", reason,
               [("announcements", "Ragnavik is going offline for planned maintenance. I will post when it is live again.")])


def maintenance_end():
    with locked_state() as state:
        maintenance = state.get("maintenance")
        if not maintenance or state["phase"] != "maintenance":
            raise RuntimeError("no maintenance window is active")
        maintenance["finished"] = True
        maintenance["until"] = min(maintenance["until"], now() + 15 * 60)


def maintenance_backup_verified():
    """Record an operator-verified pre-update backup, never routine hourly copies."""
    with locked_state() as state:
        if state.get("phase") != "maintenance" or not state.get("maintenance"):
            raise RuntimeError("backup notice requires an active maintenance window")
        if state["maintenance"].get("backup_announced"):
            raise RuntimeError("verified backup notice already sent for this window")
        record(state, "backup_verified", "pre-update rollback backup verified",
               [("logs", "Ragnavik's pre-update rollback backup has been created and verified. Maintenance can proceed.")])
        state["maintenance"]["backup_announced"] = True



def announce_live():
    latest = latest_client_pack(public_json(CLIENT_PACK_API))
    with locked_state() as state:
        state["client_pack_version"] = latest["version"]
        state["client_pack_published_at"] = latest["published_at"]
        state["client_pack_title"] = latest["title"]
        state["client_pack_notes"] = latest["notes"]
        record(state, "live", "operator confirmed server listening",
               [("announcements", recovery_message(state))])
        state["phase"] = "live"
        state.pop("down_since", None)
        state.pop("maintenance", None)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run")
    sub.add_parser("status")
    sub.add_parser("announce-live")
    maintenance = sub.add_parser("maintenance")
    maintenance_sub = maintenance.add_subparsers(dest="action", required=True)
    start = maintenance_sub.add_parser("start")
    start.add_argument("reason")
    start.add_argument("--hours", type=float, default=6)
    maintenance_sub.add_parser("end")
    maintenance_sub.add_parser("backup-verified")
    args = parser.parse_args()
    if args.command == "run":
        run()
    elif args.command == "status":
        with locked_state() as state:
            print(json.dumps(state, indent=2, sort_keys=True))
    elif args.command == "announce-live":
        announce_live()
    elif args.action == "start":
        if not 0 < args.hours <= 72:
            parser.error("--hours must be between 0 and 72")
        maintenance_start(args.reason, args.hours)
    elif args.action == "backup-verified":
        maintenance_backup_verified()
    else:
        maintenance_end()


if __name__ == "__main__":
    main()
