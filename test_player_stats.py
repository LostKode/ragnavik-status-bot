import unittest

from player_stats import boss_leaderboard_message, level_leaderboard_message, server_stats_message


class PlayerStatsTests(unittest.TestCase):
    def test_server_summary_uses_player_facing_fields(self):
        message = server_stats_message({"phase": "live", "online_count": 3,
                                        "total_deaths": 12, "latest_boss": "Fader",
                                        "client_pack_version": "1.1.34"})
        self.assertIn("Status: Live", message)
        self.assertIn("Players online: 3", message)
        self.assertIn("Recorded deaths: 12", message)
        self.assertIn("Latest boss defeat: Fader", message)
        self.assertIn("Client pack: v1.1.34", message)

    def test_level_and_boss_leaderboards_format_rankings(self):
        levels = level_leaderboard_message({"level_leaderboard": [
            {"name": "Vivi", "level": 42}, {"name": "Ragnavik", "level": 20}]})
        bosses = boss_leaderboard_message({"boss_leaderboard": [
            {"name": "Vivi", "bosses": 3}, {"name": "Ragnavik", "bosses": 1}]})
        self.assertIn("1. Vivi: level 42", levels)
        self.assertIn("1. Vivi: 3 bosses", bosses)
        self.assertIn("2. Ragnavik: 1 boss", bosses)


if __name__ == "__main__":
    unittest.main()
