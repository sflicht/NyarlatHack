"""History-removal and multi-response policy for next-use W/F. Synthetic only."""

import json
import unittest

from chaos.history import HistoryState, public_context
from chaos.next_use_history import eligible_families, next_use_menu
from test_director import event
from test_episodes import action, enabled, session, wire


def rows(*actions):
    data = [enabled(), session(2)]
    for operation, fact in actions:
        action(data, operation, fact)
    for row in data:
        row.update(sanity=60, budget=6)
    data.append(event(len(data) + 1, turn=30, sanity=60, budget=6))
    return data


def state(*actions):
    return HistoryState(wire(*rows(*actions)))


class NextUseHistoryTests(unittest.TestCase):
    def test_eligibility_is_family_presence_not_wording(self):
        empty = state()
        whistle = state(("whistling", "sound_high"))
        fountain = state(("fountain_drink", "water_refreshed"))
        foul = state(("fountain_drink", "water_foul"))
        both = state(
            ("whistling", "sound_high"),
            ("fountain_drink", "water_refreshed"),
        )
        self.assertEqual(eligible_families(empty), ())
        self.assertEqual(eligible_families(whistle), ("W",))
        self.assertEqual(eligible_families(fountain), ("F",))
        self.assertEqual(eligible_families(foul), ())
        self.assertEqual(eligible_families(both), ("W", "F"))
        self.assertEqual(
            json.loads(whistle.summary())["observed"]["turn"],
            json.loads(fountain.summary())["observed"]["turn"],
        )

    def test_same_history_offers_multiple_ops_one_origin(self):
        history = state(("whistling", "sound_normal"))
        menu = next_use_menu(history)
        self.assertEqual([row["op"] for row in menu], ["quiet", "whistle_attention"])
        self.assertEqual({row["origin"]["root_seq"] for row in menu}, {3})
        self.assertEqual({row["family"] for row in menu}, {"W"})

    def test_history_removal_drops_only_the_removed_family(self):
        both = state(
            ("whistling", "sound_humming"),
            ("fountain_drink", "water_refreshed"),
        )
        without_whistle = state(("fountain_drink", "water_refreshed"))
        without_fountain = state(("whistling", "sound_humming"))
        self.assertEqual(eligible_families(both), ("W", "F"))
        self.assertEqual(eligible_families(without_whistle), ("F",))
        self.assertEqual(eligible_families(without_fountain), ("W",))
        self.assertFalse(
            any(row["family"] == "W" for row in next_use_menu(without_whistle))
        )
        self.assertFalse(
            any(row["family"] == "F" for row in next_use_menu(without_fountain))
        )

    def test_stale_or_incomplete_origins_are_not_substituted(self):
        blocked = state(("fountain_drink", "water_foul"))
        detection = state(("fountain_drink", "detection_presented"))
        self.assertEqual(eligible_families(blocked), ())
        self.assertEqual(eligible_families(detection), ())
        self.assertEqual(next_use_menu(blocked), [])
        self.assertEqual(next_use_menu(detection), [])

    def test_public_context_carries_next_use_without_host_proof(self):
        whistle = state(("whistling", "sound_high"))
        public = public_context(whistle)
        self.assertEqual(public["next_use"]["families"], ["W"])
        self.assertEqual(
            [row["op"] for row in public["next_use"]["menu"]],
            ["quiet", "whistle_attention"],
        )
        encoded = json.dumps(public, ensure_ascii=True, separators=(",", ":"))
        self.assertLessEqual(len(encoded.encode("ascii")), 6144)
        self.assertNotIn("sha256", encoded)
