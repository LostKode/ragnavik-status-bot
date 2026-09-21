"""Formatting for additional player-facing Ragnavik commands."""

CAUSE_NAMES = {
    "EnemyHit": "Enemy attack",
    "PlayerHit": "Player attack",
    "EdgeOfWorld": "Edge of world",
    "CinderFire": "Cinder fire",
    "AshlandsOcean": "Ashlands ocean",
    "AshlandsLava": "Ashlands lava",
    "DrawBridge": "Drawbridge",
}


def friendly_label(value):
    if not value:
        return "None"
    parts = value.split(":", 1)
    raw_kind = parts[0].removeprefix("$")
    kind = CAUSE_NAMES.get(raw_kind, raw_kind.replace("_", " ").title())
    if len(parts) == 1:
        return kind
    subject = parts[1].strip().replace("_", " ").removeprefix("$").title()
    return f"{kind}: {subject}"


def online_message(state):
    count = state.get("online_count")
    if count is None:
        return "The online count is waiting for the server's first player snapshot."
    return f"{count} {'player is' if count == 1 else 'players are'} online in Ragnavik."


def records_message(state):
    records = []
    levels = state.get("level_leaderboard") or []
    deaths = state.get("death_leaderboard") or []
    bosses = state.get("boss_leaderboard") or []
    if levels:
        records.append(f"Highest level: {levels[0]['name']} at level {levels[0]['level']}")
    if bosses:
        records.append(f"Most bosses defeated: {bosses[0]['name']} with {bosses[0]['bosses']}")
    if deaths:
        records.append(f"Most deaths: {deaths[0]['name']} with {deaths[0]['deaths']}")
    return "Ragnavik records:\n" + "\n".join(records) if records else "No player records have been collected yet."


def milestones_message(state):
    milestones = state.get("milestone_history")
    if not milestones:
        return "No player milestones have been recorded yet."
    return "Recent Ragnavik milestones:\n" + "\n".join(
        f"{item['at']}: {item['message']}" for item in milestones[-10:][::-1])


def world_message(state):
    day = state.get("world_day")
    fraction = state.get("world_day_fraction")
    if day is None or fraction is None:
        return "World information is waiting for the server's first report."
    total_minutes = round(float(fraction) * 24 * 60) % (24 * 60)
    hour, minute = divmod(total_minutes, 60)
    event = friendly_label(state.get("active_event"))
    return f"Ragnavik world:\nDay: {day}\nWorld time: {hour:02d}:{minute:02d}\nActive raid: {event}"


def graveyard_message(state):
    deaths = state.get("recent_deaths")
    if not deaths:
        return "No player deaths have been recorded yet."
    return "Recent Ragnavik deaths:\n" + "\n".join(
        f"{item['name']}: {friendly_label(item['cause'])} at {item['at']}"
        for item in deaths[-10:][::-1])
