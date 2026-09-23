import unittest

from more_commands import graveyard_message, logs_message, milestones_message, online_message, records_message, world_message


class MoreCommandTests(unittest.TestCase):
    def test_online_and_records(self):
        self.assertEqual(online_message({"online_count": 1}), "1 player is online in Ragnavik.")
        message = records_message({
            "level_leaderboard": [{"name": "Vivi", "level": 42}],
            "boss_leaderboard": [{"name": "Ragnavik", "bosses": 5}],
            "death_leaderboard": [{"name": "Vivi", "deaths": 9}],
        })
        self.assertIn("Highest level: Vivi at level 42", message)
        self.assertIn("Most bosses defeated: Ragnavik with 5", message)
        self.assertIn("Most deaths: Vivi with 9", message)

    def test_world_milestones_and_graveyard(self):
        world = world_message({"world_day": 120, "world_day_fraction": 0.5,
                               "active_event": "army_eikthyr"})
        self.assertIn("Day: 120", world)
        self.assertIn("World time: 12:00", world)
        self.assertIn("Active raid: Army Eikthyr", world)
        milestones = milestones_message({"milestone_history": [
            {"at": "2026-09-21T00:00:00+00:00", "message": "Vivi reached EpicMMO level 40"}]})
        self.assertIn("Vivi reached EpicMMO level 40", milestones)
        graveyard = graveyard_message({"recent_deaths": [
            {"at": "2026-09-21T00:00:00+00:00", "name": "Vivi",
             "cause": "EnemyHit: $enemy_troll"}]})
        self.assertIn("Vivi: Enemy attack: Enemy Troll", graveyard)

    def test_logs_message_has_complete_submission_checklist(self):
        message = logs_message()
        self.assertIn("BepInEx/LogOutput.log", message)
        self.assertIn("#help-and-support", message)
        self.assertIn("close Valheim", message)
        self.assertIn("what you expected", message)
        self.assertIn("https://www.ragnavik.com/blog/sending-valheim-logs", message)
        self.assertLessEqual(len(message), 1900)


if __name__ == "__main__":
    unittest.main()
