"""Pet-visible sensitivity is not baseline-v2 and never reads engine state."""

import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import sweep_player
from sweep_screen import Screen


class PetDecisionTest(unittest.TestCase):
    def player(self, policy, rendered):
        p = sweep_player.Player.__new__(sweep_player.Player)
        p.params = sweep_player.POLICIES[policy]
        p.screen = Screen()
        p.screen.feed(rendered + b"\x1b[10;10H@\x1b[10;10H")
        p.whistle = "w"
        p.rng = mock.Mock()
        p.rng.random.return_value = 0.0
        p.last_prayer = None
        p.no_food_until = 0
        p.act = mock.Mock(return_value="whistle")
        p.explore = mock.Mock(return_value="explore")
        return p

    def decide(self, policy, rendered):
        p = self.player(policy, rendered)
        result = p.step_v2({"hp": 20, "hp_max": 20, "hunger": None, "turn": 50}, 1)
        p.rng.random.assert_called_once_with()
        return result

    def test_sensitivity_does_not_whistle_without_a_visible_pet(self):
        self.assertEqual(self.decide("pet-visible-v1", b""), "explore")

    def test_sensitivity_does_not_mistake_a_wild_dog_for_pet(self):
        self.assertEqual(self.decide("pet-visible-v1", b"\x1b[5;5Hd"), "explore")

    def test_blue_pet_background_allows_whistle(self):
        self.assertEqual(
            self.decide("pet-visible-v1", b"\x1b[5;5H\x1b[44md\x1b[0m"),
            "whistle",
        )

    def test_message_highlight_is_not_a_pet(self):
        self.assertEqual(
            self.decide("pet-visible-v1", b"\x1b[1;1H\x1b[44md\x1b[0m"),
            "explore",
        )

    def test_repainted_pet_no_longer_qualifies(self):
        self.assertEqual(
            self.decide(
                "pet-visible-v1",
                b"\x1b[5;5H\x1b[44md\x1b[0m\x1b[5;5Hd",
            ),
            "explore",
        )

    def test_erased_pet_no_longer_qualifies(self):
        for erase in (b"\x1b[2J", b"\x1b[5;1H\x1b[K"):
            with self.subTest(erase=erase):
                self.assertEqual(
                    self.decide("pet-visible-v1", b"\x1b[5;5H\x1b[44md\x1b[0m" + erase),
                    "explore",
                )

    def test_split_sgr_and_indexed_blue_are_visible(self):
        p = self.player("pet-visible-v1", b"")
        p.screen.feed(b"\x1b[5;5H\x1b[4")
        p.screen.feed(b"4md\x1b[0m\x1b[10;10H")
        self.assertTrue(p.pet_in_view())
        for code in (b"44", b"48;5;4"):
            with self.subTest(code=code):
                self.assertEqual(
                    self.decide(
                        "pet-visible-v1", b"\x1b[5;5H\x1b[" + code + b"md\x1b[m"
                    ),
                    "whistle",
                )

    def test_background_reset_and_foreground_channels_are_not_pets(self):
        for code in (b"44;49", b"38;5;44", b"38;2;44;0;0", b"41", b"104"):
            with self.subTest(code=code):
                self.assertEqual(
                    self.decide(
                        "pet-visible-v1", b"\x1b[5;5H\x1b[" + code + b"md\x1b[0m"
                    ),
                    "explore",
                )

    def test_status_hero_and_object_pile_do_not_qualify(self):
        for rendered in (
            b"\x1b[24;1H\x1b[44md\x1b[0m",
            b"\x1b[5;5H\x1b[44m(\x1b[0m",
        ):
            with self.subTest(rendered=rendered):
                self.assertEqual(self.decide("pet-visible-v1", rendered), "explore")
        p = self.player("pet-visible-v1", b"")
        p.screen.feed(b"\x1b[10;10H\x1b[44m@\x1b[0m\x1b[10;10H")
        self.assertFalse(p.pet_in_view())

    def test_baseline_whistles_without_pet(self):
        self.assertEqual(self.decide("baseline-v2", b""), "whistle")

    def test_only_sensitivity_enables_explicit_public_pet_highlighting(self):
        _, baseline = sweep_player._with_options("name:Test")
        _, pet = sweep_player._with_options("name:Test", policy="pet-visible-v1")
        self.assertEqual(baseline, "name:Test,!mail")
        self.assertEqual(pet, baseline + ",color,hilite_pet,!hilite_obj_piles")


class PetPolicyTest(unittest.TestCase):
    def test_sensitivity_report_identifies_actual_options_and_not_gate(self):
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "sweep_report_pet_test", root / "scripts/seed_sweep.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(
                policy="pet-visible-v1", game_dir=Path(tmp), out=Path(tmp) / "report"
            )
            with mock.patch.object(module, "sha256", return_value="a" * 64):
                module.write_report(args, 1, 100, ["bard-default-path"], [])
            identity = json.loads(args.out.with_suffix(".json").read_text())["identity"]
            self.assertIn("sensitivity", identity)
            self.assertEqual(
                identity["sensitivity"]["purpose"], "policy sensitivity, not the gate"
            )
            self.assertEqual(
                identity["sensitivity"]["start_options"]["bard-default-path"],
                sweep_player._with_options(None, "pet-visible-v1")[1],
            )
            self.assertEqual(identity["sensitivity"]["screen_source_sha256"], "a" * 64)
            args.policy = "baseline-v2"
            with mock.patch.object(module, "sha256", return_value="a" * 64):
                module.write_report(args, 1, 100, ["bard-default-path"], [])
            identity = json.loads(args.out.with_suffix(".json").read_text())["identity"]
            self.assertNotIn("sensitivity", identity)
            self.assertEqual(
                identity["starts"]["bard-default-path"],
                "chaos.ordinary_start.OPTIONS,!mail",
            )

    def test_separately_named_policy_leaves_baseline_unchanged(self):
        baseline = {
            "version": 2,
            "max_turns": 2000,
            "max_dlvl": 5,
            "max_commands": 8000,
            "stall_commands": 200,
            "no_food_retry_turns": 200,
            "p_whistle": 0.03,
            "p_fountain": 0.25,
            "fountain_quaffs_per_level": 2,
            "min_turns_per_level": 300,
            "p_search": 0.05,
            "p_travel_explore": 0.8,
            "prayer_gap_turns": 1000,
            "save_restore_turn": 700,
            "min_prayer_turn": 100,
            "flee_in_trouble": True,
            "rest_below": 0.67,
            "rest_command": "20s",
            "p_seek_tool": 0.5,
            "p_fountain_no_whistle": 1.0,
            "travel_retries": 3,
            "settle_pages": 400,
        }
        self.assertEqual(sweep_player.POLICIES["baseline-v2"], baseline)
        self.assertIn("pet-visible-v1", sweep_player.POLICIES)
        self.assertEqual(
            sweep_player.POLICIES["pet-visible-v1"],
            {**baseline, "whistle_only_visible_pet": True},
        )
        self.assertIsNot(
            sweep_player.POLICIES["pet-visible-v1"],
            sweep_player.POLICIES["baseline-v2"],
        )
