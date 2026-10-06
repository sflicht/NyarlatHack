"""Contract fixtures for the separate capture player, never native evidence."""

import hashlib
import json
from pathlib import Path
import random
import tempfile
from unittest.mock import Mock, patch
import unittest

from curio_capture_player import CaptureGame, CapturePlayer
from gameplay_support import Game
from sweep_player import POLICIES, Player
from sweep_screen import Screen


class CapturePlayerTests(unittest.TestCase):
    def test_save_is_copied_and_hashed_before_restore_can_consume_it(self):
        with tempfile.TemporaryDirectory() as temp:
            g = CaptureGame.__new__(CaptureGame)
            g.root = Path(temp)
            g.game = g.root / "game"
            source = g.game / "save" / "player.gz"
            source.parent.mkdir(parents=True)
            payload = b"unit-test save fixture, not native evidence"
            source.write_bytes(payload)
            with patch.object(Game, "save", return_value=0):
                self.assertEqual(g.save(), 0)
            preserved = g.root / "save-snapshots" / "0001" / "player.gz"
            self.assertTrue(preserved.is_file())
            source.unlink()  # Native restore would consume the original.
            self.assertEqual(preserved.read_bytes(), payload)
            manifest = json.loads((preserved.parent / "manifest.json").read_text())
            self.assertEqual(
                manifest["player.gz"]["sha256"], hashlib.sha256(payload).hexdigest()
            )

    def test_finish_accepts_only_the_named_reveal_question(self):
        g = CaptureGame.__new__(CaptureGame)
        g.pid, g.fd = 123, 456
        g.save_artifacts = Mock()
        g.send = Mock(side_effect=[b"Inventory? [ynq]", b"reveal rows (end)", b""])
        with (
            patch(
                "gameplay_support.os.waitpid",
                side_effect=[(0, 0), (0, 0), (0, 0), (123, 0)],
            ),
            patch("gameplay_support.os.close"),
            patch("gameplay_support.time.sleep"),
        ):
            self.assertEqual(
                g.finish(b"Do you want to know what watched you? [ynq]"), 0
            )
        self.assertEqual(
            [call.args[0] for call in g.send.call_args_list], ["y", "n", " "]
        )

    def test_separate_name_factory_and_parameters_leave_gate_registry_unchanged(self):
        from unittest.mock import sentinel

        registry = json.dumps(POLICIES, sort_keys=True)
        with (
            patch(
                "curio_capture_player.CaptureGame", return_value=sentinel.capture
            ) as capture,
            patch("sweep_player.Game", return_value=sentinel.stock),
        ):
            p = CapturePlayer(
                Path("build"),
                Path("clock"),
                Path("run"),
                17,
                "bard",
                "curio-capture-v1",
                None,
            )
        self.assertEqual(p.policy, "curio-capture-v1")
        self.assertIs(p.game, sentinel.capture)
        self.assertTrue(capture.call_args.kwargs["ordinary"])
        self.assertEqual(json.dumps(POLICIES, sort_keys=True), registry)
        self.assertNotIn(p.policy, POLICIES)
        self.assertIsNot(p.params, POLICIES["baseline-v2"])

    def test_pickup_only_inspects_new_public_inventory_entries(self):
        p = self.player()
        p._inventory = Mock(
            side_effect=[
                ({"a": "whistle"}, None),
                ({"a": "whistle", "q": "odd tool"}, None),
            ]
        )
        p.inspect_and_apply = Mock(return_value=None)
        p.pickup_tool()
        p.act.assert_called_once_with(",")
        p.inspect_and_apply.assert_called_once_with("q")

    def test_public_pile_menu_selects_tools_before_generic_settle(self):
        p = self.player()
        p.act = Player.act.__get__(p)
        p.commands, p.log = 0, []
        p.exited = Mock(return_value=False)
        p.sync_director = Mock()
        p._inventory = Mock(
            side_effect=[({}, None), ({"a": "an unfamiliar tool"}, None)]
        )
        p.inspect_and_apply = Mock(return_value=None)
        p.send = Mock(
            side_effect=[
                b"Pick up what?\nTools\na - an unfamiliar tool\n"
                b"Comestibles\nb - a food ration\n(end)",
                b"a - an unfamiliar tool.",
            ]
        )
        p.pickup_tool()
        self.assertEqual([c.args[0] for c in p.send.call_args_list], [",", "(\n"])
        p.inspect_and_apply.assert_called_once_with("a")

    def test_pickup_pages_messages_before_handling_the_pile_menu(self):
        p = self.player()
        p._pickup_menu_pending = True
        p.exited = Mock(return_value=False)
        p.send = Mock(
            side_effect=[
                b"Pick up what?\nTools\na - a tool\n(1 of 2)",
                b"a - a tool.",
            ]
        )
        p.settle(b"You see several objects here.--More--")
        self.assertEqual([c.args[0] for c in p.send.call_args_list], [" ", "(\n"])

    def test_unrelated_or_unrequested_menus_are_still_cancelled(self):
        for pending, text in (
            (False, b"Pick up what?\nTools\na - a tool\n(end)"),
            (True, b"What do you want to drop?\nTools\na - a tool\n(end)"),
        ):
            with self.subTest(pending=pending, text=text):
                p = self.player()
                p._pickup_menu_pending = pending
                p.exited = Mock(return_value=False)
                p.send = Mock(return_value=b"")
                p.settle(text)
                p.send.assert_called_once_with("\x1b")

    def player(self):
        p = CapturePlayer.__new__(CapturePlayer)
        p.screen = Screen()
        p.screen.x, p.screen.y = 5, 5
        p.screen.rows[5][5] = "@"
        p.params = dict(POLICIES["baseline-v2"])
        p.rng = random.Random(1)
        p.whistle = "a"
        p.quaffs, p.travel_short, p.visited = {}, {}, {}
        p.not_fountains = set()
        p.level_since = {1: 0, 2: 0}
        p.commands, p.log = 0, []
        p.exited = Mock(return_value=False)
        p.send = Mock(return_value=b"There is a staircase down here.")
        p.act = Mock(return_value=None)
        return p

    def test_walks_toward_visible_stair_instead_of_chasing_highlighted_pet(self):
        p = self.player()
        for x in range(6, 10):
            p.screen.rows[5][x] = "·"
        p.screen.rows[5][6] = "d"
        p.screen.backgrounds[5][6] = 4
        p.screen.rows[5][9] = ">"
        # The move past the pet is the first route step, not a combat priority.
        p.explore({"turn": 400}, 1, (5, 5))
        p.screen.rows[5][6] = "·"
        p.screen.rows[6][5] = "d"
        p.screen.backgrounds[6][5] = 4
        p.act.reset_mock()
        p.explore({"turn": 401}, 1, (5, 5))
        p.act.assert_called_once_with("l")

    def test_visible_tool_is_explored_before_known_stairs(self):
        p = self.player()
        p.screen.rows[5][4] = "("
        p.screen.rows[5][6] = ">"
        p.explore({"turn": 400}, 1, (5, 5))
        p.act.assert_called_once_with("h")

    def test_known_stair_survives_blank_redraw_and_is_not_shared_across_levels(self):
        p = self.player()
        p.screen.rows[5][6] = ">"
        p.explore({"turn": 400}, 1, (5, 5))
        p.screen.rows[5][5] = " "
        p.screen.rows[5][6] = "@"
        p.screen.x = 6
        p.act.reset_mock()
        p.explore({"turn": 401}, 1, (6, 5))
        p.act.assert_called_once_with(">")
        p.act.reset_mock()
        p.explore({"turn": 402}, 2, (6, 5))
        p.act.assert_called_once_with("10s")

    def test_dwells_min_turns_per_level_before_descending(self):
        p = self.player()
        p.level_since = {1: 100}
        p.screen.rows[5][6] = ">"
        p.screen.rows[5][4] = "·"
        p.explore({"turn": 399}, 1, (5, 5))
        self.assertNotEqual(p.act.call_args.args[0], "l")
        p.act.reset_mock()
        p.screen.rows[5][5] = ">"
        p.screen.rows[5][6] = "·"
        p.explore({"turn": 399}, 1, (5, 5))
        self.assertNotEqual(p.act.call_args.args[0], ">")
        p.act.reset_mock()
        p.explore({"turn": 400}, 1, (5, 5))
        p.act.assert_called_once_with(">")

    def test_arriving_by_branch_staircase_climbs_back_and_never_retakes_it(self):
        p = self.player()
        p.screen.rows[5][5] = ">"
        p.screen.rows[5][6] = "·"
        p.map_memory = {3: {(1, 1): "·"}}
        p.visited[3] = {(1, 1)}
        p.level_since[3] = 401
        p.send = Mock(return_value=b"There is a branch staircase up here.")
        with patch("curio_capture_player.status", return_value={"dlvl": 3}):
            p.explore({"turn": 400}, 2, (5, 5))
        p.send.assert_called_once_with(":")  # public look only after arrival
        self.assertEqual([c.args[0] for c in p.act.call_args_list], [">", "<"])
        self.assertIn((2, (5, 5)), p.branch_stairs)
        # The branch level's memory never leaks into main-dungeon level 3.
        self.assertNotIn(3, p.map_memory)
        self.assertNotIn(3, p.visited)
        self.assertNotIn(3, p.level_since)
        p.send.reset_mock()
        p.act.reset_mock()
        p.explore({"turn": 401}, 2, (5, 5))
        p.send.assert_not_called()
        self.assertNotEqual(p.act.call_args.args[0], ">")

    def test_arriving_by_main_staircase_stays(self):
        p = self.player()
        p.screen.rows[5][5] = ">"
        p.send = Mock(return_value=b"There is a staircase up here.")
        with patch("curio_capture_player.status", return_value={"dlvl": 3}):
            p.explore({"turn": 400}, 2, (5, 5))
        p.send.assert_called_once_with(":")
        p.act.assert_called_once_with(">")

    def test_does_not_route_through_unseen_stone(self):
        p = self.player()
        p.screen.rows[5][8] = ">"
        p.explore({"turn": 400}, 1, (5, 5))
        p.act.assert_called_once_with("10s")

    def test_paginated_public_inventory_describes_before_applying(self):
        p = self.player()
        script = iter(
            [
                ("i", b"a - a whistle\n(1 of 2)"),
                (" ", b"q - an Unfamiliar tool\n(end)"),
                ("q", b"I - Describe this item\na - Apply this item\n(end)"),
                ("I", b"A description supplied by the game.\n(end)"),
            ]
        )

        def send(key):
            expected, text = next(script)
            self.assertEqual(key, expected)
            p.screen.feed(b"\x1b[2J\x1b[H" + text)
            return text

        p.send = Mock(side_effect=send)
        p.settle = Mock(return_value=None)
        p.inspect_and_apply("q")
        self.assertEqual(p.send.call_count, 4)
        p.settle.assert_called_once_with(b"A description supplied by the game.\n(end)")
        p.act.assert_called_once_with("aq")

    def test_unrecognized_inventory_action_menu_does_not_apply(self):
        p = self.player()
        outputs = iter([b"q - a tool\n(end)", b"Unexpected menu (end)", b""])

        def send(key):
            text = next(outputs)
            p.screen.feed(b"\x1b[2J\x1b[H" + text)
            return text

        p.send = Mock(side_effect=send)
        p.inspect_and_apply("q")
        p.act.assert_not_called()
        self.assertEqual([c.args[0] for c in p.send.call_args_list], ["i", "q", "\x1b"])

    def test_arriving_on_remembered_tool_attempts_pickup_once(self):
        p = self.player()
        p.map_memory = {1: {(5, 5): "("}}
        p.pickup_tool = Mock(side_effect=lambda: setattr(p, "pickup_succeeded", True))
        p.explore({"turn": 400}, 1, (5, 5))
        p.explore({"turn": 401}, 1, (5, 5))
        p.pickup_tool.assert_called_once_with()

    def test_failed_pickup_retries_boundedly_without_claiming_success(self):
        p = self.player()
        p.map_memory = {1: {(5, 5): "("}}
        p.pickup_tool = Mock(return_value=None)
        for turn in range(400, 405):
            p.explore({"turn": turn}, 1, (5, 5))
        self.assertEqual(p.pickup_tool.call_count, 3)
        self.assertNotIn((1, (5, 5)), p.pickup_tried)

    def test_failed_public_step_is_not_retried_forever(self):
        p = self.player()
        p.screen.rows[5][6] = ">"
        for turn in range(400, 404):
            p.explore({"turn": turn}, 1, (5, 5))
        self.assertEqual(
            [c.args[0] for c in p.act.call_args_list], ["l", "l", "l", "10s"]
        )

    def test_search_moves_between_exhausted_public_edges(self):
        p = self.player()
        p.screen.rows[5][6] = "·"
        p.visited = {1: {(5, 5), (6, 5)}}
        p.explore({"turn": 400}, 1, (5, 5))
        p.explore({"turn": 410}, 1, (5, 5))
        self.assertEqual([c.args[0] for c in p.act.call_args_list], ["10s", "l"])

    def test_closed_door_is_opened_before_walking(self):
        p = self.player()
        p.screen.rows[5][6] = "▒"
        p.screen.rows[5][7] = ">"
        p.explore({"turn": 400}, 1, (5, 5))
        p.act.assert_called_once_with("ol")

    def test_open_confirmation_allows_walking_through_same_door_glyph(self):
        for confirmation in ("The door opens.", "This door is already open."):
            with self.subTest(confirmation=confirmation):
                p = self.player()
                p.screen.rows[5][6] = "▒"
                p.screen.rows[5][7] = ">"

                def act(key):
                    p.screen.rows[0] = list(confirmation.ljust(80))
                    return None

                p.act.side_effect = act
                p.explore({"turn": 400}, 1, (5, 5))
                p.explore({"turn": 401}, 1, (5, 5))
                self.assertEqual([c.args[0] for c in p.act.call_args_list], ["ol", "l"])

    def test_start_enables_public_pet_highlight_and_restores_process_options(self):
        import chaos.ordinary_start as start

        p = self.player()
        p.start_name, p.fed = "bard", 0
        p.game = Mock(raw=bytearray())
        observed = []
        p.game.start.side_effect = lambda: observed.append(start.OPTIONS) or b""
        p.settle = Mock(return_value=None)
        original = start.OPTIONS
        p._start()
        self.assertIn(",color,hilite_pet,!hilite_obj_piles", observed[0])
        self.assertEqual(start.OPTIONS, original)
        self.assertEqual(p.seek_whistle(1, (5, 5)), (False, None))

    def test_only_public_blue_background_exempts_a_monster(self):
        p = CapturePlayer.__new__(CapturePlayer)
        p.screen = Screen()
        p.screen.x, p.screen.y = 5, 5
        p.screen.rows[5][5] = "@"
        p.screen.rows[5][6] = "d"
        p.screen.backgrounds[5][6] = 4
        p.screen.rows[5][4] = "d"
        self.assertEqual(p.monsters((5, 5)), [(4, 5)])
        self.assertEqual(Player.monsters(p, (5, 5)), [(4, 5), (6, 5)])


if __name__ == "__main__":
    unittest.main()
