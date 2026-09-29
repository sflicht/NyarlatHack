"""#198: `chaos play --ordinary` turns the echo hound and next-use on by default.

Offline: the fake game from test_launcher reports its environment, so these
tests see exactly what the launcher installed and exported. No game build.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_launcher import GAME, ROOT

HAUNT_DEFAULT = ROOT / "chaos" / "packs" / "footsteps.lua"

GAME_ENV = GAME.replace(
    "nethackoptions=os.environ.get('NETHACKOPTIONS'))",
    "nethackoptions=os.environ.get('NETHACKOPTIONS'),\n"
    "            admit=os.environ.get('NYARLATHACK_NEXT_USE_ADMIT'),\n"
    "            observations=os.environ.get('NYARLATHACK_OBSERVATIONS'))",
)
assert GAME_ENV != GAME


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX/Linux process fixtures")
class OrdinaryDefaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.root = self.path / "game root"
        self.root.mkdir()
        game = self.root / "dnethack"
        game.write_text(GAME_ENV)
        game.chmod(0o700)
        self.marker = self.path / "started.json"
        self.env = dict(os.environ, GAME_MARKER=str(self.marker), TMPDIR=str(self.path))

    def run_cli(self, *args):
        if self.marker.exists():
            self.marker.unlink()
        return subprocess.run(
            [sys.executable, "-m", "chaos", "play", "--game-root", str(self.root)]
            + list(args),
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=20,
        )

    def fresh(self, name, *args):
        run = self.path / name
        result = self.run_cli("--run-dir", str(run), *args)
        return run, result

    def info(self):
        return json.loads(self.marker.read_text())

    def choice(self, run):
        return json.loads((run / "ordinary-choice.json").read_text())

    def assert_haunt(self, run, on):
        self.assertEqual((run / "haunting.lua").exists(), on)
        if on:
            self.assertEqual(
                (run / "haunting.lua").read_bytes(), HAUNT_DEFAULT.read_bytes()
            )

    def assert_next_use(self, on):
        info = self.info()
        self.assertEqual(info["admit"], "1" if on else None)
        self.assertEqual(info["observations"], "1" if on else None)

    def test_fresh_ordinary_defaults_both_on_and_records_choice(self):
        run, result = self.fresh("defaults", "--ordinary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_haunt(run, True)
        self.assert_next_use(True)
        choice = self.choice(run)
        self.assertEqual(
            {k: choice[k] for k in ("v", "haunt", "next_use")},
            dict(v=1, haunt=True, next_use=True),
        )
        self.assertEqual(choice["haunt_pack"], str(HAUNT_DEFAULT))
        self.assertEqual(os.stat(run / "ordinary-choice.json").st_mode & 0o777, 0o600)

    def test_opt_outs_restore_todays_behaviour_exactly(self):
        run, result = self.fresh("off", "--ordinary", "--no-haunt", "--no-next-use")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_haunt(run, False)
        self.assert_next_use(False)
        self.assertEqual(
            self.choice(run),
            dict(v=1, haunt=False, haunt_pack=None, haunt_sha256=None, next_use=False),
        )
        for flags, haunt, next_use in (
            (("--no-haunt",), False, True),
            (("--no-next-use",), True, False),
            (("--haunt", "--next-use"), True, True),  # old recipes still work
        ):
            with self.subTest(flags=flags):
                run, result = self.fresh("-".join(flags), "--ordinary", *flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assert_haunt(run, haunt)
                self.assert_next_use(next_use)

    def test_conflicting_flags_refused(self):
        for flags in (("--haunt", "--no-haunt"), ("--next-use", "--no-next-use")):
            with self.subTest(flags=flags):
                _, result = self.fresh("conflict", "--ordinary", *flags)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())

    def test_non_ordinary_play_keeps_opt_in(self):
        run, result = self.fresh("plain")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_haunt(run, False)
        self.assert_next_use(False)
        self.assertFalse((run / "ordinary-choice.json").exists())

    def test_restore_follows_recorded_choice_not_todays_defaults(self):
        run, result = self.fresh(
            "recorded", "--ordinary", "--no-haunt", "--no-next-use"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = (run / "ordinary-choice.json").read_bytes()
        result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_haunt(run, False)
        self.assert_next_use(False)
        self.assertEqual((run / "ordinary-choice.json").read_bytes(), record)
        # A restore flag that contradicts the record fails closed before the game.
        result = self.run_cli("--ordinary", "--haunt", "--reuse-run-dir", str(run))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertFalse((run / "haunting.lua").exists())

    def test_restore_of_default_run_verifies_the_recorded_pack(self):
        run, result = self.fresh("both", "--ordinary")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_haunt(run, True)
        self.assert_next_use(True)

    def test_restore_of_pre_198_run_directory_is_unchanged(self):
        # A run directory from before #198 has no choice record: only the
        # explicit flags apply, exactly as they did when the run started.
        run = self.path / "old"
        run.mkdir(mode=0o700)
        result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_haunt(run, False)
        self.assert_next_use(False)
        self.assertFalse((run / "ordinary-choice.json").exists())

    def test_invalid_choice_record_fails_closed(self):
        for raw in (b"{}", b"[]", b'{"v":2}', b"not json"):
            with self.subTest(raw=raw):
                run = self.path / ("bad-" + str(len(raw)) + raw[:2].hex())
                run.mkdir(mode=0o700)
                target = run / "ordinary-choice.json"
                target.write_bytes(raw)
                target.chmod(0o600)
                result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
