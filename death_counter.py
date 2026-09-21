"""Player-facing death leaderboard formatting."""


def death_leaderboard_message(state):
    leaderboard = state.get("death_leaderboard")
    if leaderboard is None:
        return "The death counter is waiting for the server's first report."
    if not leaderboard:
        return "No player deaths have been recorded yet."
    lines = []
    for position, player in enumerate(leaderboard[:10], start=1):
        deaths = player["deaths"]
        lines.append(f"{position}. {player['name']}: {deaths} {'death' if deaths == 1 else 'deaths'}")
    total = sum(player["deaths"] for player in leaderboard)
    return "Ragnavik death leaderboard:\n" + "\n".join(lines) + f"\nTotal recorded deaths: {total}"
