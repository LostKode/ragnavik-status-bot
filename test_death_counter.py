import unittest

from death_counter import death_leaderboard_message


class DeathCounterTests(unittest.TestCase):
    def test_leaderboard_orders_counts_and_uses_singular_grammar(self):
        message = death_leaderboard_message({"death_leaderboard": [
            {"name": "Vivi", "deaths": 4},
            {"name": "Ragnavik", "deaths": 1},
        ]})
        self.assertIn("1. Vivi: 4 deaths", message)
        self.assertIn("2. Ragnavik: 1 death", message)
        self.assertIn("Total recorded deaths: 5", message)


if __name__ == "__main__":
    unittest.main()
