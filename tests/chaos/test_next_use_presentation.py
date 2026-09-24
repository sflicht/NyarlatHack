"""Bound presentation requests: real TTY, fake unsupported port, no game claim."""

import json
import os
import subprocess
import unittest

import test_next_use_dogmove as dogmove


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUsePresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the existing linked native fixture and controlled-RNG object set.
        dogmove.NextUseDogMoveTests.setUpClass()
        cls.root = dogmove.NextUseDogMoveTests.root
        cls.exe = cls.root / "presentation"
        print("NEXT_USE_PRESENTATION_ARTIFACTS=" + str(cls.root), flush=True)
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(dogmove.ROOT / "include"),
                str(dogmove.ROOT / "tests/chaos/next_use_presentation.c"),
                *map(str, dogmove.NextUseDogMoveTests.objects),
                "-lncursesw",
                "-ltinfo",
                "-lm",
                *subprocess.check_output(
                    ["pkg-config", "--libs", "lua5.4"], text=True
                ).split(),
                "-o",
                str(cls.exe),
            ],
            check=True,
            capture_output=True,
            timeout=45,
        )

    def case(self, name):
        directory = self.root / name
        directory.mkdir(mode=0o700)
        env = dict(os.environ, TERM="xterm", COLUMNS="80", LINES="24")
        run = subprocess.run(
            [str(self.exe), name],
            cwd=directory,
            env=env,
            capture_output=True,
            timeout=10,
        )
        (directory / "stdout").write_bytes(run.stdout)
        (directory / "stderr").write_bytes(run.stderr)
        self.assertEqual(run.returncode, 0, run.stderr)
        value = json.loads((directory / "presentation-result.json").read_text())
        self.assertEqual(value["repeat"], 0, value)
        self.assertEqual(value["fake_calls"], 0, value)
        return value

    def test_real_tty_delivers_once_and_cancelled_map_cannot_retry(self):
        self.assertEqual(self.case("positive")["result"], 3)
        self.assertEqual(self.case("cancelled")["result"], 2)

    def test_fake_unsupported_backend_does_not_use_an_unrelated_redraw(self):
        self.assertEqual(self.case("unsupported")["result"], 1)

    def test_stale_or_changed_bindings_fail_closed(self):
        for name in (
            "root",
            "generation",
            "game",
            "level",
            "turn",
            "monster_turn",
            "identity",
            "hidden",
            "glyph",
            "replacement",
        ):
            with self.subTest(name=name):
                value = self.case(name)
                self.assertEqual(value["begin"], 1)
                self.assertEqual(value["result"], 0, value)

    def test_preexisting_glyph_must_match_exactly(self):
        value = self.case("pre_glyph")
        self.assertEqual(value["begin"], 0)
        self.assertEqual(value["result"], 0)

    def test_copied_request_cannot_publish_or_cancel_the_original(self):
        value = self.case("copy")
        self.assertEqual(value["result"], 0)
        self.assertEqual(value["original"], 3)


if __name__ == "__main__":
    unittest.main()
