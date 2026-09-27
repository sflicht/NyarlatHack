"""Fresh --ordinary over an existing save is refused before launch (#175).

Real launcher subprocesses with a fake game; no native build or save format.
"""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

from test_director import current_event
from test_launcher import GAME, ROOT

from chaos.launcher import _ordinary_name
from chaos.ordinary_start import OPTIONS


def _snapshot(path):
    """Names, bytes, modes and mtimes of every entry below path."""
    out = {}
    for p in sorted(path.rglob("*")):
        s = p.lstat()
        out[str(p.relative_to(path))] = (
            s.st_mode,
            s.st_mtime_ns,
            p.read_bytes() if p.is_file() else None,
        )
    return out


class OrdinaryNameTests(unittest.TestCase):
    def test_name_follows_game_precedence_and_save_regularization(self):
        env = dict(NETHACKOPTIONS=OPTIONS, USER="someone")
        self.assertEqual(_ordinary_name(env, []), "ChaosReview")
        self.assertEqual(_ordinary_name(env, ["-u", "Other"]), "Other")
        self.assertEqual(_ordinary_name(env, ["-uA.b c"]), "A_b_c")
        self.assertEqual(_ordinary_name(dict(USER="x-Brd"), []), "x")
        self.assertIsNone(_ordinary_name(dict(NETHACKOPTIONS="@/some/file"), []))


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX/Linux process fixtures")
class OrdinarySaveRefusalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)
        self.root = self.path / "game root"
        self.root.mkdir()
        (self.root / "dnethack").write_text(GAME)
        (self.root / "dnethack").chmod(0o700)
        (self.root / "save").mkdir()
        self.save = self.root / "save" / (str(os.getuid()) + "ChaosReview")
        self.marker = self.path / "started.json"
        self.env = dict(os.environ, GAME_MARKER=str(self.marker), TMPDIR=str(self.path))
        for name in ("NETHACKOPTIONS", "NETHACKDIR", "HACKDIR"):
            self.env.pop(name, None)

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "chaos", "play", "--game-root", str(self.root)]
            + list(args),
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
        )

    def runs(self):
        return sorted(
            p for p in self.path.iterdir() if p.name.startswith("nyarlathack-")
        )

    def make_run(self, name="nyarlathack-original"):
        """A launcher-style run that began a new game and never ended."""
        run = self.path / name
        run.mkdir(mode=0o700)
        # Before the default pack's safe index, so a real restore is valid.
        rows = [
            current_event(1, event="session", detail="new", turn=1, safe=0),
            current_event(2, event="level_enter", detail="", turn=1, safe=0),
        ]
        (run / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (run / "events.jsonl").chmod(0o600)
        return run

    def write_save(self):
        self.save.write_bytes(b"opaque save bytes")
        later = time.time() + 5
        os.utime(self.save, (later, later))

    def assert_refused(self, result, before):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("refusing a fresh ordinary run", result.stderr)
        self.assertIn(json.dumps(str(self.save)), result.stderr)
        self.assertIn("nothing was launched", result.stderr)
        self.assertFalse(self.marker.exists(), "game must not start")
        self.assertEqual(_snapshot(self.path), before, "no file may change")

    def test_refusal_names_save_run_and_exact_resume_command(self):
        run = self.make_run()
        self.write_save()
        before = _snapshot(self.path)
        result = self.run_cli("--ordinary")
        self.assert_refused(result, before)
        self.assertEqual(self.runs(), [run], "no new run directory")
        self.assertIn(json.dumps(str(run)), result.stderr)
        command = shlex.join(
            [
                "python3", "-m", "chaos", "play", "--ordinary",
                "--game-root", str(self.root.resolve()),
                "--reuse-run-dir", str(run),
            ]
        )  # fmt: skip
        self.assertIn("  " + command + "\n", result.stderr)
        self.assertIn("mv " + shlex.quote(str(self.save)), result.stderr)

    def test_refusal_without_owning_run_explains_how_to_start_fresh(self):
        ended = self.make_run("nyarlathack-ended")
        with (ended / "events.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    current_event(3, event="death", detail="quit", turn=1, safe=0)
                )
                + "\n"
            )
        self.write_save()
        before = _snapshot(self.path)
        result = self.run_cli("--ordinary", "--next-use")
        self.assert_refused(result, before)
        self.assertIn("no single run directory", result.stderr)
        self.assertNotIn("--reuse-run-dir", result.stderr)
        self.assertIn("mv " + shlex.quote(str(self.save)), result.stderr)

    def test_refusal_ignores_runs_written_after_the_save(self):
        self.write_save()
        past = self.save.stat().st_mtime - 60
        os.utime(self.save, (past, past))
        self.make_run()
        result = self.run_cli("--ordinary")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("no single run directory", result.stderr)

    def test_fresh_ordinary_start_without_save_launches(self):
        self.make_run()  # An unrelated earlier run does not block a fresh start.
        result = self.run_cli("--ordinary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("refusing", result.stderr)
        info = json.loads(self.marker.read_text())
        self.assertEqual(info["nethackoptions"], OPTIONS)
        self.assertEqual(len(self.runs()), 2)

    def test_reuse_run_dir_with_save_still_launches(self):
        run = self.make_run()
        self.write_save()
        result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("refusing", result.stderr)
        self.assertEqual(json.loads(self.marker.read_text())["run"], str(run))
        self.assertEqual(self.save.read_bytes(), b"opaque save bytes")

    def test_non_ordinary_play_is_unchanged(self):
        self.write_save()
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
