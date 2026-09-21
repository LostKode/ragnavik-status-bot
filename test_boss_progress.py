import unittest

from boss_progress import boss_progress_message


class BossProgressTests(unittest.TestCase):
    def test_message_lists_player_totals_and_deep_north_boss(self):
        message = boss_progress_message({"boss_player_counts": {
            "defeated_eikthyr": 2,
            "defeated_frozenking": 1,
        }})
        self.assertIn("Eikthyr: 2 players", message)
        self.assertIn("Kall Fimbulbringer: 1 player", message)
        self.assertIn("Fader: 0 players", message)


if __name__ == "__main__":
    unittest.main()
