"""Synthetic next-use composition tests. No native admission or model spend."""

import json
import tempfile
import unittest
from pathlib import Path

from chaos.history import public_context
from chaos.history_choice import OAuthHistoryBackend, RandomHistoryBackend
from chaos.next_use_compose import composition_candidates, compose, lua_source
from chaos.next_use_install import install
from test_next_use_history import state


CONTEXT = {
    "history_context_v": 1,
    "summary": {"observed": {"turn": 20}, "recent": []},
    "episodes": {"episodes": []},
    "prior_whispers": [],
    "prior_coverage": {"shown": 0, "omitted": 0},
    "next_use": {"families": [], "menu": []},
}


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.deadline = float("inf")
        self.calls = []
        self.receipt = {"synthetic_transport": True}

    def generate(self, instructions, prompt, *, return_receipt=False):
        self.calls.append((instructions, prompt, return_receipt))
        return self.response, self.receipt


class NextUseComposeTests(unittest.TestCase):
    def test_both_families_compose_cross_family_effects(self):
        both = state(("whistling", "sound_high"), ("fountain_drink", "water_refreshed"))
        menu = composition_candidates(both)
        self.assertEqual(
            [row["op"] for row in menu], ["whistle_attention", "fountain_refresh"]
        )
        self.assertEqual([row["family"] for row in menu], ["W", "F"])

    def test_one_family_offers_quiet_and_effect(self):
        whistle = state(("whistling", "sound_normal"))
        menu = composition_candidates(whistle)
        self.assertEqual([row["op"] for row in menu], ["quiet", "whistle_attention"])

    def test_lua_is_bounded_printable_ascii(self):
        source = lua_source("whistle_attention").encode("ascii")
        self.assertLessEqual(len(source), 4096)
        self.assertNotIn(b"\0", source)
        self.assertIn(b"on_action", source)
        self.assertIn(b"whistle_attention", source)

    def test_random_choice_stays_inside_frozen_menu(self):
        both = state(("whistling", "sound_high"), ("fountain_drink", "water_refreshed"))
        menu = composition_candidates(both)
        context = public_context(both)
        chosen = RandomHistoryBackend(0).choose_next_use(context, menu)
        self.assertIn(chosen, menu)

    def test_oauth_selects_exact_menu_row_without_inventing_lua(self):
        both = state(("whistling", "sound_high"), ("fountain_drink", "water_refreshed"))
        menu = composition_candidates(both)
        context = public_context(both)
        transport = FakeTransport(json.dumps(menu[1], separators=(",", ":")))
        chosen = OAuthHistoryBackend(transport).choose_next_use(context, menu)
        self.assertEqual(chosen, menu[1])
        self.assertEqual(len(transport.calls), 1)

    def test_install_is_not_admission(self):
        selected = composition_candidates(state(("fountain_drink", "water_refreshed")))[
            1
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            path.chmod(0o700)
            receipt = install(path, selected)
            self.assertEqual(receipt["status"], "candidate_installed_not_admitted")
            self.assertEqual(receipt["op"], "fountain_refresh")
            self.assertEqual(
                receipt["source_sha256"], compose(selected)["source_sha256"]
            )
            target = path / "next_use.lua"
            self.assertEqual(
                target.read_bytes().decode("ascii"), lua_source("fountain_refresh")
            )
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
