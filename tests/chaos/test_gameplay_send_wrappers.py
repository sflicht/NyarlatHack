"""Offline unit harness for the actual nested driver send overrides.

Compile only the trusted local class definitions, never the native driver main
functions. Replace their supervision bases with Game to exercise real send and
finish without launching an engine or constructing native fixtures.
"""

import ast
from pathlib import Path
import unittest
from unittest.mock import call, patch

from gameplay_support import Game


WRAPPERS = (
    ("test_episode_turnloop.py", "OwnedGame"),
    ("test_episode_fountain_fatal.py", "FrozenGame"),
)


def load_wrapper(filename, name):
    path = Path(__file__).with_name(filename)
    tree = ast.parse(path.read_text(), filename=str(path))
    classes = [
        n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == name
    ]
    if len(classes) != 1:
        raise AssertionError(f"expected one actual {name} definition in {path}")
    # Keep the complete, unmodified class body, including its guards and super().
    namespace = {
        "Game": Game,
        "OwnedGame": Game,
        "owned_game_type": lambda base, cancel: base,
        "cancel": None,
    }
    module = ast.Module(body=[classes[0]], type_ignores=[])
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


class SendWrapperTests(unittest.TestCase):
    def game(self, wrapper):
        cls = load_wrapper(*wrapper)
        game = cls.__new__(cls)
        game.pid, game.fd = 123, 456
        game.inputs = []
        game.raw = bytearray()
        game._reader_pid = None
        game.frozen_inputs = ["6e"] * 3
        return game

    def test_actual_wrappers_forward_deadline_to_base_send(self):
        for wrapper in WRAPPERS:
            for value in ("n", b"n"):
                with self.subTest(wrapper=wrapper, value=value):
                    game = self.game(wrapper)
                    with patch.object(Game, "send", return_value=b"reply") as send:
                        self.assertEqual(game.send(value, deadline=7.5), b"reply")
                    send.assert_called_once_with(value, deadline=7.5)

    def test_actual_wrappers_preserve_default_calls(self):
        for wrapper in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                game = self.game(wrapper)
                with patch("gameplay_support.os.write") as write:
                    with patch.object(game, "read", return_value=b"reply") as read:
                        self.assertEqual(game.send("n"), b"reply")
                write.assert_called_once_with(456, b"n")
                read.assert_called_once_with()
                self.assertEqual(game.inputs, ["6e"])

    def test_real_finish_shares_prompt_deadline_through_actual_wrappers(self):
        for wrapper in WRAPPERS:
            with self.subTest(wrapper=wrapper):
                game = self.game(wrapper)
                now = 0.0
                budgets = []

                def read(initial=3.0):
                    nonlocal now
                    budgets.append(initial)
                    now += initial
                    return b"[ynq]"

                with (
                    patch("gameplay_support.time.monotonic", lambda: now),
                    patch("gameplay_support.os.waitpid", return_value=(0, 0)),
                    patch("gameplay_support.os.write") as write,
                    patch.object(game, "read", side_effect=read),
                ):
                    with self.assertRaisesRegex(AssertionError, "game failed to exit"):
                        Game.finish(game, b"[ynq]")
                self.assertEqual(budgets, [3.0, 3.0, 2.0])
                self.assertEqual(now, 8.0)
                self.assertEqual(game.inputs, ["6e"] * 3)
                self.assertEqual(write.call_args_list, [call(456, b"n")] * 3)
                self.assertEqual((game.pid, game.fd), (123, 456))

    def assert_guard(self, game, value, message):
        before = list(game.inputs)
        with patch.object(Game, "send") as send:
            with self.assertRaisesRegex(AssertionError, message):
                game.send(value, deadline=7.5)
        send.assert_not_called()
        self.assertEqual(game.inputs, before)

    def test_owned_batch_cap_precedes_parent_send(self):
        game = self.game(WRAPPERS[0])
        game.inputs = ["6e"] * 80
        self.assert_guard(game, b"n", "input batch cap")

    def test_owned_byte_cap_precedes_parent_send(self):
        game = self.game(WRAPPERS[0])
        game.inputs = [(b"n" * 2048).hex()]
        self.assert_guard(game, b"n", "input byte cap")

    def test_frozen_cap_precedes_parent_send(self):
        game = self.game(WRAPPERS[1])
        game.inputs = list(game.frozen_inputs)
        self.assert_guard(game, b"n", "input cap")

    def test_frozen_exact_input_guard_precedes_parent_send(self):
        for value in ("y", b"y"):
            with self.subTest(value=value):
                self.assert_guard(self.game(WRAPPERS[1]), value, "unplanned input")


if __name__ == "__main__":
    unittest.main()
