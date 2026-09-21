"""Player-facing server summary and progression leaderboard formatting."""


def server_stats_message(state):
    phase = state.get("phase", "unknown").title()
    online = state.get("online_count")
    online_text = "Waiting for a player snapshot" if online is None else str(online)
    deaths = state.get("total_deaths", 0)
    latest_boss = state.get("latest_boss") or "None recorded yet"
    version = state.get("client_pack_version") or "Unknown"
    return ("Ragnavik server stats:\n"
            f"Status: {phase}\n"
            f"Players online: {online_text}\n"
            f"Recorded deaths: {deaths}\n"
            f"Latest boss defeat: {latest_boss}\n"
            f"Client pack: v{version}")


def level_leaderboard_message(state):
    leaderboard = state.get("level_leaderboard")
    if leaderboard is None:
        return "The level leaderboard is waiting for the server's first player snapshot."
    if not leaderboard:
        return "No player levels have been recorded yet."
    lines = [f"{position}. {player['name']}: level {player['level']}"
             for position, player in enumerate(leaderboard[:10], start=1)]
    return "Ragnavik EpicMMO leaderboard:\n" + "\n".join(lines)


def boss_leaderboard_message(state):
    leaderboard = state.get("boss_leaderboard")
    if leaderboard is None:
        return "The boss leaderboard is waiting for the server's first private key report."
    if not leaderboard:
        return "No named players have recorded private boss progress yet."
    lines = []
    for position, player in enumerate(leaderboard[:10], start=1):
        bosses = player["bosses"]
        lines.append(f"{position}. {player['name']}: {bosses} {'boss' if bosses == 1 else 'bosses'}")
    return "Ragnavik boss leaderboard:\n" + "\n".join(lines)
