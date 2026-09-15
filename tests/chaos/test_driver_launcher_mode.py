"""Driver-only launcher mode tests; never execute the launcher or native game."""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from gameplay_support import Game, ROOT


class ExecCaptured(Exception):
    """Stop the mocked child branch without starting a process."""


class DriverLauncherModeTests(unittest.TestCase):
    def setUp(self):
        modules_before = set(sys.modules)
        held = {
            "test_curio_failure_gameplay",
            "test_curio_gameplay",
            "test_curio_restart_gameplay",
        }
        self.addCleanup(
            lambda: self.assertFalse(
                held.intersection(
                    name.rsplit(".", 1)[-1]
                    for name in set(sys.modules) - modules_before
                )
            )
        )
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "source"
        self.source.mkdir(mode=0o700)
        for name in ("dnethack", "nhdat", "license"):
            path = self.source / name
            path.write_bytes(b"private fake " + name.encode())
            path.chmod(0o600)
        self.preload = self.root / "fake-preload"
        self.preload.write_bytes(b"not a shared library")
        self.preload.chmod(0o600)

        self.enterContext(
            patch("gameplay_support.pty.fork", side_effect=AssertionError("real fork"))
        )
        self.enterContext(
            patch("gameplay_support.os.execve", side_effect=AssertionError("real exec"))
        )

    def capture_start(self, game):
        with (
            patch("gameplay_support.pty.fork", return_value=(0, -1)),
            patch("gameplay_support.os.chdir") as chdir,
            patch("gameplay_support.os.execve", side_effect=ExecCaptured) as execve,
            self.assertRaises(ExecCaptured),
        ):
            game.start()
        chdir.assert_called_once_with(game.game)
        execve.assert_called_once()
        return execve.call_args.args

    def test_default_launcher_precreates_private_run(self):
        game = Game(
            self.source, self.preload, root=self.root / "session", launcher_options=[]
        )
        self.assertTrue(game.run.is_dir())
        self.assertEqual(game.run.stat().st_mode & 0o777, 0o700)

    def test_fresh_launcher_leaves_run_absent(self):
        game = Game(
            self.source,
            self.preload,
            root=self.root / "session",
            launcher_options=[],
            launcher_fresh=True,
        )
        self.assertFalse(game.run.exists())
        self.assertTrue(game.game.is_dir())
        for name in ("dnethack", "nhdat", "license"):
            self.assertEqual(
                (game.game / name).read_bytes(), (self.source / name).read_bytes()
            )
        for name in ("perm", "record", "logfile", "xlogfile", "livelog"):
            self.assertEqual((game.game / name).read_bytes(), b"")
        for name in ("save", "dumplog"):
            self.assertTrue((game.game / name).is_dir())

    def test_fresh_direct_exec_rejected_before_any_resource_write(self):
        with patch("gameplay_support.tempfile.mkdtemp") as mkdtemp:
            with self.assertRaisesRegex(ValueError, "launcher_options"):
                Game(self.source, self.preload, launcher_fresh=True)
        mkdtemp.assert_not_called()
        root = self.root / "not-created"
        with self.assertRaisesRegex(ValueError, "launcher_options"):
            Game(self.source, self.preload, root=root, launcher_fresh=True)
        self.assertFalse(root.exists())

    def test_fresh_constructor_rejects_existing_run_without_repair(self):
        for game_exists in (False, True):
            for kind in ("directory", "file", "dangling-symlink"):
                with self.subTest(game_exists=game_exists, kind=kind):
                    root = self.root / f"existing-{game_exists}-{kind}"
                    root.mkdir(mode=0o700)
                    if game_exists:
                        (root / "game").mkdir()
                    run = root / "run"
                    if kind == "directory":
                        run.mkdir(mode=0o755)
                        (run / "evidence").write_bytes(b"retain")
                    elif kind == "file":
                        run.write_bytes(b"retain")
                    else:
                        run.symlink_to(root / "missing")
                    before = run.lstat()
                    with self.assertRaises(FileExistsError):
                        Game(
                            self.source,
                            self.preload,
                            root=root,
                            launcher_options=[],
                            launcher_fresh=True,
                        )
                    self.assertEqual(run.lstat(), before)
                    self.assertEqual((root / "game").exists(), game_exists)
                    if kind == "directory":
                        self.assertEqual((run / "evidence").read_bytes(), b"retain")
                    elif kind == "file":
                        self.assertEqual(run.read_bytes(), b"retain")
                    else:
                        self.assertEqual(run.readlink(), root / "missing")

    def test_fresh_existing_game_root_still_leaves_run_absent(self):
        game = Game(self.source, self.preload, root=self.root / "session")
        game.run.rmdir()  # Private fixture setup, not driver recovery.
        before = (game.game / "dnethack").stat()
        fresh = Game(
            self.root / "missing-source",
            self.preload,
            root=game.root,
            launcher_options=[],
            launcher_fresh=True,
        )
        self.assertFalse(fresh.run.exists())
        self.assertEqual((fresh.game / "dnethack").stat(), before)

    def test_launcher_argv_preserves_options_and_explicit_mode(self):
        for options in (
            [],
            ["--curio-source", "/private/source.lua"],
            [
                "--curio-bundle-root",
                "/private/bundles",
                "--curio-candidate-id",
                "a" * 64,
            ],
        ):
            for fresh in (False, True):
                for wizard in (False, True):
                    with self.subTest(options=options, fresh=fresh, wizard=wizard):
                        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
                        game = Game(
                            self.source,
                            self.preload,
                            root=root,
                            launcher_options=options,
                            launcher_fresh=fresh,
                            wizard=wizard,
                        )
                        executable, args, env = self.capture_start(game)
                        self.assertEqual(executable, sys.executable)
                        self.assertEqual(
                            args,
                            [
                                sys.executable,
                                "-m",
                                "chaos",
                                "play",
                                "--run-dir" if fresh else "--reuse-run-dir",
                                str(game.run),
                                "--game-root",
                                str(game.game),
                                *options,
                                "--",
                                *(["-D", "-u", "wizard"] if wizard else []),
                            ],
                        )
                        self.assertEqual(env["PYTHONPATH"], str(ROOT))
                        self.assertEqual(game.launcher_options, options)

    def test_default_launcher_argv_is_legacy_reuse(self):
        game = Game(
            self.source, self.preload, root=self.root / "session", launcher_options=[]
        )
        _, args, _ = self.capture_start(game)
        self.assertEqual(
            args,
            [
                sys.executable,
                "-m",
                "chaos",
                "play",
                "--reuse-run-dir",
                str(game.run),
                "--game-root",
                str(game.game),
                "--",
            ],
        )

    def test_reuse_is_explicit_not_inferred_from_existing_run(self):
        game = Game(
            self.source,
            self.preload,
            root=self.root / "session",
            launcher_options=[],
            launcher_fresh=True,
        )
        self.assertIn("--run-dir", self.capture_start(game)[1])
        # Simulated launcher publication/save: no native acceptance is claimed.
        game.run.mkdir(mode=0o700)
        evidence = game.run / "curio-install.json"
        evidence.write_bytes(b"opaque retained evidence")
        evidence.chmod(0o600)
        before = evidence.stat()
        self.assertIn("--run-dir", self.capture_start(game)[1])
        self.assertTrue(game.launcher_fresh)
        game.launcher_fresh = False
        args = self.capture_start(game)[1]
        self.assertIn("--reuse-run-dir", args)
        self.assertNotIn("--run-dir", args)
        self.assertEqual(evidence.stat(), before)
        self.assertEqual(evidence.read_bytes(), b"opaque retained evidence")

    def test_missing_run_does_not_implicitly_switch_reuse_to_fresh(self):
        game = Game(
            self.source, self.preload, root=self.root / "session", launcher_options=[]
        )
        game.run.rmdir()
        self.assertIn("--reuse-run-dir", self.capture_start(game)[1])
        self.assertFalse(game.run.exists())

    def test_direct_exec_fresh_property_rejected_before_start_bookkeeping(self):
        game = Game(self.source, self.preload, root=self.root / "session")
        game.launcher_fresh = True
        with self.assertRaisesRegex(ValueError, "launcher_options"):
            game.start()
        self.assertEqual(game.sessions, [])

    def test_environment_and_direct_argv_remain_unchanged(self):
        for launcher in (False, True):
            for observe in (False, True):
                for wizard in (False, True):
                    for echoes in (False, True):
                        with self.subTest(
                            launcher=launcher,
                            observe=observe,
                            wizard=wizard,
                            echoes=echoes,
                        ):
                            root = Path(
                                self.enterContext(tempfile.TemporaryDirectory())
                            )
                            game = Game(
                                self.source,
                                self.preload,
                                root=root,
                                observe=observe,
                                wizard=wizard,
                                echoes=echoes,
                                launcher_options=[] if launcher else None,
                            )
                            inherited = {
                                "PATH": "/inherited/bin",
                                "PYTHONPATH": "/inherited/python",
                                "NYARLATHACK_RUN_DIR": "/must-not-leak",
                                "OTHER": "retained",
                            }
                            with patch.dict(os.environ, inherited, clear=True):
                                executable, args, env = self.capture_start(game)
                            expected = dict(
                                inherited,
                                TERM="xterm",
                                TZ="UTC",
                                HOME=str(game.root),
                                LD_PRELOAD=str(self.preload),
                                NETHACKOPTIONS="name:ChaosReview,role:Wizard,race:human,gender:male,align:neutral,windowtype:tty,!news,!legacy,time",
                                NYARLATHACK_ECHOES="1" if echoes else "0",
                            )
                            expected.pop("NYARLATHACK_RUN_DIR")
                            if observe:
                                expected["NYARLATHACK_RUN_DIR"] = str(game.run)
                            if launcher:
                                expected["PYTHONPATH"] = str(ROOT)
                            else:
                                self.assertEqual(executable, "./dnethack")
                                self.assertEqual(
                                    args,
                                    ["./dnethack"]
                                    + (["-D", "-u", "wizard"] if wizard else []),
                                )
                            self.assertEqual(env, expected)


if __name__ == "__main__":
    unittest.main()
