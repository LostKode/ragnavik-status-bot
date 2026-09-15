"""Authenticated Phoenix control API and Discord message delivery on the worker."""
import json
import os
from pathlib import Path
import urllib.request

BOT_TOKEN_FILE = os.environ.get("DISCORD_BOT_TOKEN_FILE", "/run/secrets/ragnavik_discord_bot_token")
CONTROL_TOKEN_FILE = os.environ.get("RAGNAVIK_CONTROL_TOKEN_FILE", "/run/secrets/ragnavik_bot_control_token")
STATUS_URL = os.environ.get("RAGNAVIK_STATUS_URL", "http://192.168.86.21:8787")
CHANNEL_ID = os.environ.get("DISCORD_STATUS_CHANNEL_ID", "1245520097758674964")
OWNER_ID = os.environ.get("DISCORD_OWNER_ID", "208311542016376833")
DISCORD_API = "https://discord.com/api/v10"


def request(url, method, payload, headers):
    data = json.dumps(payload).encode() if payload is not None else None
    call = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(call, timeout=10) as response:
        return json.load(response) if response.status != 204 else None


def control(method, path, payload=None):
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
        dm = discord_request(token, "POST", "/users/@me/channels", {"recipient_id": OWNER_ID})
        channel_id = dm["id"]
    else:
        channel_id = CHANNEL_ID
    discord_request(token, "POST", f"/channels/{channel_id}/messages",
                    {"content": item["message"], "allowed_mentions": {"parse": []},
                     "nonce": item["nonce"][:25], "enforce_nonce": True})
