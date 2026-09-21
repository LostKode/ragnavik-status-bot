#!/usr/bin/env python3
"""Ragnavik slash commands and transition delivery on a worker node."""
import asyncio
from pathlib import Path
import urllib.error

import discord
from anticheat_receiver import start_receiver
from discord import app_commands

from bot_api import BOT_TOKEN_FILE, OWNER_ID, control, deliver
from boss_progress import boss_progress_message
from death_counter import death_leaderboard_message

PACK_URL = "https://valheim.hexium.gg/mods/LostKode/Ragnavik"
GUIDE_URL = "https://ragnavik.vercel.app/blog/getting-started"
async def phoenix(method, path, payload=None):
    return await asyncio.to_thread(control, method, path, payload)


class RagnavikBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents(guilds=True))
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.anticheat_server = None
        self.anticheat_queue = None
        try:
            self.anticheat_server, self.anticheat_queue = start_receiver()
        except RuntimeError as exc:
            print(f"Ragnavik anti-cheat intake disabled: {exc}", flush=True)
        self.delivery_task = asyncio.create_task(self.delivery_loop())
        await self.tree.sync()

    async def delivery_loop(self):
        while True:
            try:
                item = (await asyncio.to_thread(self.anticheat_queue.next)
                        if self.anticheat_queue is not None else None)
                if item:
                    await asyncio.to_thread(deliver, item)
                    await asyncio.to_thread(self.anticheat_queue.ack, item["id"])
                else:
                    item = await phoenix("GET", "/events")
                    if item:
                        await asyncio.to_thread(deliver, item)
                        await phoenix("POST", "/ack", {"id": item["id"]})
            except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
                print(f"Ragnavik delivery pending: {exc}", flush=True)
            await asyncio.sleep(5)


client = RagnavikBot()
group = app_commands.Group(name="ragnavik", description="Ragnavik server information")


@group.command(name="latest", description="Show the latest Ragnavik modpack download page")
async def latest(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Latest Ragnavik modpack: {PACK_URL}\nHexium shows the newest published version there.",
        ephemeral=True)


@group.command(name="status", description="Show whether the server is live or in maintenance")
async def status(interaction: discord.Interaction):
    try:
        state = await phoenix("GET", "/state")
    except (OSError, urllib.error.URLError):
        await interaction.response.send_message("Server status is temporarily unavailable.", ephemeral=True)
        return
    phase = state["phase"]
    if phase == "live":
        message = "Ragnavik is live."
    elif phase == "maintenance":
        message = f"Ragnavik is in maintenance: {state['maintenance']['reason']}."
    elif phase == "offline":
        message = "Ragnavik is offline. The announcements channel has the outage details."
    else:
        message = "Ragnavik status is initializing."
    await interaction.response.send_message(message, ephemeral=True)


@group.command(name="bosses", description="Show how many players have defeated each world boss")
async def bosses(interaction: discord.Interaction):
    try:
        state = await phoenix("GET", "/state")
    except (OSError, urllib.error.URLError):
        await interaction.response.send_message("Boss progress is temporarily unavailable.", ephemeral=True)
        return
    message = boss_progress_message(state)
    await interaction.response.send_message(message[:1900], ephemeral=True)


@group.command(name="deaths", description="Show the Ragnavik player death leaderboard")
async def deaths(interaction: discord.Interaction):
    try:
        state = await phoenix("GET", "/state")
    except (OSError, urllib.error.URLError):
        await interaction.response.send_message("The death counter is temporarily unavailable.", ephemeral=True)
        return
    await interaction.response.send_message(death_leaderboard_message(state)[:1900], ephemeral=True)


@group.command(name="guide", description="Show the Ragnavik getting started guide")
async def guide(interaction: discord.Interaction):
    await interaction.response.send_message(f"Ragnavik guide: {GUIDE_URL}", ephemeral=True)


@group.command(name="recent", description="Show recent server status changes")
async def recent(interaction: discord.Interaction):
    if interaction.user.id != int(OWNER_ID):
        await interaction.response.send_message("This command is for the server owner.", ephemeral=True)
        return
    try:
        entries = await phoenix("GET", "/recent")
    except (OSError, urllib.error.URLError):
        await interaction.response.send_message("Status history is temporarily unavailable.", ephemeral=True)
        return
    message = ("\n".join(f"{item['at']}: {item['kind']} ({item['reason']})" for item in entries)
               if entries else "No status changes have been recorded yet.")
    await interaction.response.send_message(message[:1900], ephemeral=True)


@group.command(name="maintenance_start", description="Announce a planned maintenance window")
@app_commands.describe(reason="What is being changed", hours="Maximum planned duration")
async def maintenance_start_command(interaction: discord.Interaction, reason: str, hours: float = 6.0):
    if interaction.user.id != int(OWNER_ID):
        await interaction.response.send_message("This command is for the server owner.", ephemeral=True)
        return
    if not 0 < hours <= 72:
        await interaction.response.send_message("Duration must be between 0 and 72 hours.", ephemeral=True)
        return
    try:
        await phoenix("POST", "/maintenance/start", {"reason": reason, "hours": hours})
    except urllib.error.HTTPError as exc:
        await interaction.response.send_message(f"Maintenance could not start (HTTP {exc.code}).", ephemeral=True)
        return
    except OSError:
        await interaction.response.send_message("Status monitor is temporarily unavailable.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Maintenance notice queued. Outage alerts are suppressed during this window.", ephemeral=True)


@group.command(name="maintenance_end", description="Finish maintenance and wait for the server to become live")
async def maintenance_end_command(interaction: discord.Interaction):
    if interaction.user.id != int(OWNER_ID):
        await interaction.response.send_message("This command is for the server owner.", ephemeral=True)
        return
    try:
        await phoenix("POST", "/maintenance/end")
    except urllib.error.HTTPError as exc:
        await interaction.response.send_message(f"Maintenance could not end (HTTP {exc.code}).", ephemeral=True)
        return
    except OSError:
        await interaction.response.send_message("Status monitor is temporarily unavailable.", ephemeral=True)
        return
    await interaction.response.send_message(
        "Maintenance is ending. The monitor will post when the server is ready.", ephemeral=True)


client.tree.add_command(group)


def main():
    token = Path(BOT_TOKEN_FILE).read_text().strip()
    if not token:
        raise RuntimeError("Discord bot token file is empty")
    client.run(token)


if __name__ == "__main__":
    main()
