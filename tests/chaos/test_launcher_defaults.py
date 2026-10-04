"""#198: `chaos play --ordinary` turns the echo hound and next-use on by default.

Offline: the fake game from test_launcher reports its environment, so these
tests see exactly what the launcher installed and exported. No game build.
"""

import hashlib
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
            {k: choice[k] for k in ("v", "haunt", "next_use", "whispers")},
            dict(v=6, haunt=True, next_use=True, whispers=dict(backend="m1", seed=0)),
        )
        self.assertEqual(
            choice["m2"],
            {"enabled": True, "cap": 3, "repair": True, "broad": True, "ring": True},
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
            dict(
                v=6,
                m2=dict(enabled=False, cap=3, repair=False, broad=False, ring=False),
                haunt=False,
                haunt_pack=None,
                haunt_sha256=None,
                next_use=False,
                whispers=dict(backend="m1", seed=0),
            ),
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

    def test_m1_menu_recorded_and_followed_on_restore(self):
        # #1 M1: --seed picks the menu seed; explicit whisper flags opt out.
        run, result = self.fresh("seeded", "--ordinary", "--seed", "9")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.choice(run)["whispers"], dict(backend="m1", seed=9))
        record = (run / "ordinary-choice.json").read_bytes()
        result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((run / "ordinary-choice.json").read_bytes(), record)
        for flags in (("--seed", "8"), ("--backend", "pack"), ("--pack", "ward")):
            with self.subTest(flags=flags):
                result = self.run_cli("--ordinary", *flags, "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())
        for flags in (
            ("--backend", "pack"),
            ("--backend", "random"),
            ("--pack", "ward"),
        ):
            with self.subTest(flags=flags):
                run, result = self.fresh("-".join(flags), "--ordinary", *flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNone(self.choice(run)["whispers"])

    def test_restore_of_v1_record_keeps_the_pack(self):
        from types import SimpleNamespace

        from chaos import launcher

        run = self.path / "v1"
        run.mkdir(mode=0o700)
        target = run / "ordinary-choice.json"
        target.write_text(
            json.dumps(
                dict(
                    v=1, haunt=False, haunt_pack=None, haunt_sha256=None, next_use=False
                )
            )
        )
        target.chmod(0o600)
        args = SimpleNamespace(
            ordinary=True,
            backend=None,
            pack=None,
            at=None,
            id=None,
            seed=None,
            ordinary_food=False,
            haunt=None,
            no_haunt=False,
            next_use=False,
            no_next_use=False,
        )
        self.assertIsNone(launcher._resolve_choice(args, run))
        self.assertIsNone(args.m1_seed)
        self.assertEqual(args.next_use_programs, 1)
        record = dict(json.loads(target.read_text()), v=2)
        for whispers, seed in ((dict(backend="m1", seed=4), 4), (None, None)):
            target.write_text(json.dumps(dict(record, whispers=whispers)))
            self.assertIsNone(launcher._resolve_choice(args, run))
            self.assertEqual(args.m1_seed, seed)
            self.assertEqual(args.next_use_programs, 1)
        for enabled, cap in ((True, 3), (False, 1)):
            target.write_text(
                json.dumps(
                    dict(
                        record,
                        v=3,
                        next_use=True,
                        whispers=None,
                        m2=dict(enabled=enabled, cap=3),
                    )
                )
            )
            args.next_use = False
            self.assertIsNone(launcher._resolve_choice(args, run))
            self.assertTrue(args.next_use)
            self.assertEqual(args.next_use_programs, cap)
            # A v3 record predates the recurrence repair and keeps its rules.
            self.assertFalse(args.next_use_repair)
        for enabled, cap in ((True, 3), (False, 1)):
            target.write_text(
                json.dumps(
                    dict(
                        record,
                        v=4,
                        next_use=True,
                        whispers=None,
                        m2=dict(enabled=enabled, cap=3, repair=enabled),
                    )
                )
            )
            args.next_use = False
            self.assertIsNone(launcher._resolve_choice(args, run))
            self.assertEqual(args.next_use_programs, cap)
            self.assertEqual(args.next_use_repair, enabled)
            # C: a v4 record keeps B's rules exactly, never broad next-use.
            self.assertFalse(args.next_use_broad)
        for enabled, cap in ((True, 3), (False, 1)):
            target.write_text(
                json.dumps(
                    dict(
                        record,
                        v=5,
                        next_use=True,
                        whispers=None,
                        m2=dict(enabled=enabled, cap=3, repair=enabled, broad=enabled),
                    )
                )
            )
            args.next_use = False
            self.assertIsNone(launcher._resolve_choice(args, run))
            self.assertEqual(args.next_use_programs, cap)
            self.assertEqual(args.next_use_repair, enabled)
            self.assertEqual(args.next_use_broad, enabled)
            # Ring: a v5 record keeps C's rules exactly, never ring.
            self.assertFalse(args.next_use_ring)
        for enabled, cap in ((True, 3), (False, 1)):
            target.write_text(
                json.dumps(
                    dict(
                        record,
                        v=6,
                        next_use=True,
                        whispers=None,
                        m2=dict(
                            enabled=enabled,
                            cap=3,
                            repair=enabled,
                            broad=enabled,
                            ring=enabled,
                        ),
                    )
                )
            )
            args.next_use = False
            self.assertIsNone(launcher._resolve_choice(args, run))
            self.assertEqual(args.next_use_programs, cap)
            self.assertEqual(args.next_use_broad, enabled)
            self.assertEqual(args.next_use_ring, enabled)

    def test_invalid_choice_record_fails_closed(self):
        base = dict(
            v=2, haunt=False, haunt_pack=None, haunt_sha256=None, next_use=False
        )
        bad_v2 = [
            dict(base),  # v2 without whispers
            dict(base, whispers=dict(backend="random", seed=0)),
            dict(base, whispers=dict(backend="m1", seed="0")),
            dict(base, whispers=dict(backend="m1", seed=-1)),
            dict(base, whispers=dict(backend="m1")),
            dict(base, v=1, whispers=None),  # v1 with a v2 key
            dict(base, v=3, whispers=None),
            dict(base, v=3, whispers=None, m2=dict(enabled=True, cap=3)),
            dict(base, v=3, whispers=None, m2=dict(enabled=False, cap=True)),
            dict(base, v=3, whispers=None, m2=dict(enabled=False, cap=4)),
            dict(base, v=3, whispers=None, m2=dict(enabled=False, cap=3, repair=False)),
            dict(base, v=4, whispers=None, m2=dict(enabled=False, cap=3)),
            dict(base, v=4, whispers=None, m2=dict(enabled=False, cap=3, repair=True)),
            dict(base, v=4, whispers=None, m2=dict(enabled=False, cap=3, repair=0)),
            dict(
                base,
                v=4,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=False),
            ),
            dict(base, v=5, whispers=None, m2=dict(enabled=False, cap=3, repair=False)),
            dict(
                base,
                v=5,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=True),
            ),
            dict(
                base,
                v=5,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=0),
            ),
            dict(
                base,
                v=6,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=False),
            ),
            # Ring (v6): ring must be present, boolean and equal to enabled;
            # a v5 record may not carry it.
            dict(
                base,
                v=6,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=False, ring=True),
            ),
            dict(
                base,
                v=6,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=False, ring=0),
            ),
            dict(
                base,
                v=5,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=False, ring=False),
            ),
            dict(
                base,
                v=7,
                whispers=None,
                m2=dict(enabled=False, cap=3, repair=False, broad=False, ring=False),
            ),
        ]
        for raw in (b"{}", b"[]", b'{"v":2}', b"not json") + tuple(
            json.dumps(r).encode() for r in bad_v2
        ):
            with self.subTest(raw=raw):
                run = self.path / ("bad-" + hashlib.sha256(raw).hexdigest()[:12])
                run.mkdir(mode=0o700)
                target = run / "ordinary-choice.json"
                target.write_bytes(raw)
                target.chmod(0o600)
                result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
