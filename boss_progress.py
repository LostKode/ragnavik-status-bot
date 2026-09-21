"""Player-facing boss progress formatting shared by the Discord command and tests."""

BOSSES = [
    ("Eikthyr", "defeated_eikthyr"),
    ("The Elder", "defeated_gdking"),
    ("Bonemass", "defeated_bonemass"),
    ("Moder", "defeated_dragon"),
    ("Yagluth", "defeated_goblinking"),
    ("The Queen", "defeated_queen"),
    ("Fader", "defeated_fader"),
    ("Kall Fimbulbringer", "defeated_frozenking"),
]


def boss_progress_message(state):
    counts = state.get("boss_player_counts")
    if counts is None:
        return "Player boss progress is waiting for the server's first private key report."
    lines = []
    for name, key in BOSSES:
        count = counts.get(key, 0)
        lines.append(f"{name}: {count} {'player' if count == 1 else 'players'}")
    known = {key for _, key in BOSSES}
    for key in sorted(set(counts) - known):
        name = key.removeprefix("defeated_").replace("_", " ").title()
        count = counts[key]
        lines.append(f"{name}: {count} {'player' if count == 1 else 'players'}")
    return "Ragnavik player boss progress:\n" + "\n".join(lines)
