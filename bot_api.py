"""Authenticated Phoenix control API and Discord message delivery on the worker."""
import json
import os
from pathlib import Path
import urllib.request

BOT_TOKEN_FILE = os.environ.get("DISCORD_BOT_TOKEN_FILE", "/run/secrets/ragnavik_discord_bot_token")
CONTROL_TOKEN_FILE = os.environ.get("RAGNAVIK_CONTROL_TOKEN_FILE", "/run/secrets/ragnavik_bot_control_token")
STATUS_URL = os.environ.get("RAGNAVIK_STATUS_URL", "")
LOG_CHANNEL_ID = os.environ.get("DISCORD_LOG_CHANNEL_ID",
                                os.environ.get("DISCORD_LOGS_CHANNEL_ID", ""))
ANNOUNCEMENTS_CHANNEL_ID = os.environ.get(
    "DISCORD_ANNOUNCEMENTS_CHANNEL_ID",
    os.environ.get("DISCORD_STATUS_CHANNEL_ID", ""))
LONGHOUSE_CHANNEL_ID = os.environ.get("DISCORD_LONGHOUSE_CHANNEL_ID", "")
# Backward-compatible names used by existing deployments and tests.
CHANNEL_ID = ANNOUNCEMENTS_CHANNEL_ID
LOGS_CHANNEL_ID = LOG_CHANNEL_ID
OWNER_ID = os.environ.get("DISCORD_OWNER_ID", "")
DISCORD_API = "https://discord.com/api/v10"


def request(url, method, payload, headers):
    data = json.dumps(payload).encode() if payload is not None else None
    call = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(call, timeout=10) as response:
        return json.load(response) if response.status != 204 else None


def control(method, path, payload=None):
    if not STATUS_URL:
        raise RuntimeError("RAGNAVIK_STATUS_URL is not configured")
    token = Path(CONTROL_TOKEN_FILE).read_text().strip()
    return request(STATUS_URL + path, method, payload, {"X-Ragnavik-Control": token})


def discord_request(token, method, path, payload):
    return request(DISCORD_API + path, method, payload,
                   {"Authorization": "Bot " + token, "User-Agent": "RagnavikStatus/1.0"})


def deliver(item):
    token = Path(BOT_TOKEN_FILE).read_text().strip()
    if not token:
        raise RuntimeError("Discord bot token file is empty")
    if item["destination"] == "dm":
        if not OWNER_ID:
            raise RuntimeError("DISCORD_OWNER_ID is not configured")
        dm = discord_request(token, "POST", "/users/@me/channels", {"recipient_id": OWNER_ID})
        channel_id = dm["id"]
    else:
        channels = {
            "channel": ANNOUNCEMENTS_CHANNEL_ID,
            "log": LOG_CHANNEL_ID,
            "logs": LOG_CHANNEL_ID,
            "announcements": ANNOUNCEMENTS_CHANNEL_ID,
            "longhouse": LONGHOUSE_CHANNEL_ID,
        }
        if item["destination"] not in channels:
            raise ValueError(f"Unknown Discord destination: {item['destination']}")
        channel_id = channels[item["destination"]]
        if not channel_id:
            raise RuntimeError(f"Discord channel is not configured for {item['destination']}")
    discord_request(token, "POST", f"/channels/{channel_id}/messages",
                    {"content": item["message"], "allowed_mentions": {"parse": []},
                     "nonce": item["nonce"][:25], "enforce_nonce": True})
