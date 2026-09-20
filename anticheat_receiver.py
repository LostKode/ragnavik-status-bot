"""Authenticated, durable anti-cheat event intake for the Discord bot worker."""
import datetime as dt
import hmac
import http.server
import json
import os
from pathlib import Path
import re
import sqlite3
import threading

ANTICHEAT_BIND = os.environ.get("RAGNAVIK_ANTICHEAT_BIND", "0.0.0.0")
ANTICHEAT_PORT = int(os.environ.get("RAGNAVIK_ANTICHEAT_PORT", "8788"))
ANTICHEAT_TOKEN_FILE = os.environ.get(
    "RAGNAVIK_ANTICHEAT_TOKEN_FILE", "/run/secrets/ragnavik_anticheat_reporter_token")
ANTICHEAT_STATE_DIR = Path(os.environ.get(
    "RAGNAVIK_BOT_STATE_DIR", "/var/lib/ragnavik-bot"))
EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
STEAM_ID = re.compile(r"^[0-9]{0,32}$")


class EventQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS events ("
                "id TEXT PRIMARY KEY, received_at TEXT NOT NULL, message TEXT NOT NULL, "
                "delivered INTEGER NOT NULL DEFAULT 0)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def enqueue(self, event_id, message):
        received = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._connect() as db:
            result = db.execute(
                "INSERT OR IGNORE INTO events (id, received_at, message) VALUES (?, ?, ?)",
                (event_id, received, message))
            return result.rowcount == 1

    def next(self):
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT id, message FROM events WHERE delivered = 0 "
                "ORDER BY received_at, id LIMIT 1").fetchone()
        if not row:
            return None
        return {"id": row[0], "destination": "log", "message": row[1],
                "nonce": "anticheat-" + row[0]}

    def ack(self, event_id):
        with self._lock, self._connect() as db:
            db.execute("UPDATE events SET delivered = 1 WHERE id = ?", (event_id,))
            db.execute(
                "DELETE FROM events WHERE delivered = 1 AND received_at < datetime('now', '-30 days')")


def _text(value, name, maximum, allow_empty=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"invalid {name}")
    value = value.strip()
    if not value and not allow_empty:
        raise ValueError(f"invalid {name}")
    return value


def validate_event(payload):
    if not isinstance(payload, dict):
        raise ValueError("event must be an object")
    allowed = {"eventId", "type", "server", "steamId", "characterName",
               "problems", "timeoutSeconds", "catosVersion"}
    if set(payload) - allowed:
        raise ValueError("unknown event fields")
    event_id = _text(payload.get("eventId"), "eventId", 120)
    if not EVENT_ID.fullmatch(event_id):
        raise ValueError("invalid eventId")
    kind = payload.get("type")
    if kind not in ("mismatch", "timeout"):
        raise ValueError("invalid type")
    server = _text(payload.get("server"), "server", 80)
    steam_id = _text(payload.get("steamId", ""), "steamId", 32, allow_empty=True)
    if not STEAM_ID.fullmatch(steam_id):
        raise ValueError("invalid steamId")
    character = _text(payload.get("characterName", ""), "characterName", 80,
                      allow_empty=True)
    catos_version = _text(payload.get("catosVersion", ""), "catosVersion", 30,
                          allow_empty=True)
    clean = {"eventId": event_id, "type": kind, "server": server,
             "steamId": steam_id, "characterName": character,
             "catosVersion": catos_version}
    if kind == "mismatch":
        problems = payload.get("problems")
        if (not isinstance(problems, list) or not 0 < len(problems) <= 20 or
                not all(isinstance(item, str) and 0 < len(item.strip()) <= 300
                        for item in problems)):
            raise ValueError("invalid problems")
        clean["problems"] = [item.strip() for item in problems]
    else:
        timeout = payload.get("timeoutSeconds")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 1 <= timeout <= 120:
            raise ValueError("invalid timeoutSeconds")
        clean["timeoutSeconds"] = timeout
    return clean


def _discord_text(value):
    return value.replace("`", "'").replace("\r", " ").replace("\n", " ")


def format_event(event):
    heading = ("**[CatosAntiCheat] Kick: mod mismatch**" if event["type"] == "mismatch"
               else "**[CatosAntiCheat] Kick: no mod-list reply**")
    lines = [f"{heading} `{_discord_text(event['server'])}`"]
    if event["characterName"]:
        lines.append(f"Character: `{_discord_text(event['characterName'])}`")
    if event["steamId"]:
        lines.append(f"Steam ID: `{event['steamId']}`")
    if not event["characterName"] and not event["steamId"]:
        lines.append("Player identity was not supplied by CatosAntiCheat.")
    if event["type"] == "mismatch":
        lines.append(f"Reasons ({len(event['problems'])}):")
        lines.extend(f"• {_discord_text(problem)}" for problem in event["problems"])
    else:
        lines.append(
            f"Reason: no response within {event['timeoutSeconds']:g}s; "
            "the client may be vanilla or missing CatosAntiCheat.")
    if event["catosVersion"]:
        lines.append(f"CatosAntiCheat: `{event['catosVersion']}`")
    return "\n".join(lines)[:1900]


def handler(queue, token_file):
    class AntiCheatHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format_string, *args):
            return

        def do_POST(self):
            if self.path != "/anticheat":
                self.send_error(404)
                return
            try:
                expected = Path(token_file).read_text().strip()
            except OSError:
                self.send_error(503)
                return
            supplied = self.headers.get("X-Ragnavik-Anticheat", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise ValueError("invalid body size")
                event = validate_event(json.loads(self.rfile.read(size)))
                inserted = queue.enqueue(event["eventId"], format_event(event))
            except (ValueError, TypeError, json.JSONDecodeError):
                self.send_error(400)
                return
            self.send_response(202 if inserted else 204)
            self.end_headers()

    return AntiCheatHandler


def start_receiver(queue=None):
    try:
        queue = queue or EventQueue(ANTICHEAT_STATE_DIR / "anticheat.sqlite3")
        server = http.server.ThreadingHTTPServer(
            (ANTICHEAT_BIND, ANTICHEAT_PORT), handler(queue, ANTICHEAT_TOKEN_FILE))
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise RuntimeError(f"receiver could not start: {exc}") from exc
    thread = threading.Thread(target=server.serve_forever, name="anticheat-receiver", daemon=True)
    thread.start()
    return server, queue
