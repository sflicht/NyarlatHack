"""`chaos play` model-authoring settings: validated before any run directory,
recorded in the choice record, followed on restore. Nothing configured keeps
today's record (v6) byte for byte.

Offline: the fake game from test_launcher; no provider is imported.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_launcher import GAME, ROOT

MODEL = "grok-test-model"  # fixture id; real runs pass --author-model
AUTHOR_ENV = ("NYARLATHACK_AUTHOR_PROVIDER", "NYARLATHACK_AUTHOR_MODEL", "XAI_API_KEY")


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX/Linux process fixtures")
class LauncherAuthorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.root = self.path / "game root"
        self.root.mkdir()
        game = self.root / "dnethack"
        game.write_text(GAME)
        game.chmod(0o700)
        self.marker = self.path / "started.json"
        self.env = {k: v for k, v in os.environ.items() if k not in AUTHOR_ENV}
        self.env.update(GAME_MARKER=str(self.marker), TMPDIR=str(self.path))

    def run_cli(self, *args, env=None):
        if self.marker.exists():
            self.marker.unlink()
        return subprocess.run(
            [sys.executable, "-m", "chaos", "play", "--game-root", str(self.root)]
            + list(args),
            cwd=ROOT,
            env=dict(self.env, **(env or {})),
            text=True,
            capture_output=True,
            timeout=20,
        )

    def fresh(self, name, *args, env=None):
        run = self.path / name
        return run, self.run_cli("--run-dir", str(run), *args, env=env)

    def choice(self, run):
        return json.loads((run / "ordinary-choice.json").read_text())

    def test_nothing_configured_keeps_the_v6_record(self):
        run, result = self.fresh("none", "--ordinary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.choice(run)["v"], 6)
        self.assertNotIn("author", self.choice(run))
        # Empty variables count as unset.
        run, result = self.fresh(
            "empty",
            "--ordinary",
            env={"NYARLATHACK_AUTHOR_PROVIDER": "", "NYARLATHACK_AUTHOR_MODEL": ""},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.choice(run)["v"], 6)

    def test_rejected_configurations_stop_before_any_run_directory(self):
        cases = [
            (("--author-model", MODEL), {}, "--author-provider"),
            (("--author-provider", "xai-oauth"), {}, "--author-model"),
            (
                ("--author-provider", "nope", "--author-model", MODEL),
                {},
                "unknown provider",
            ),
            ((), {"NYARLATHACK_AUTHOR_MODEL": MODEL}, "NYARLATHACK_AUTHOR_PROVIDER"),
            ((), {"NYARLATHACK_AUTHOR_PROVIDER": "xai"}, "NYARLATHACK_AUTHOR_MODEL"),
            (
                (
                    "--author-provider",
                    "xai-oauth",
                    "--author-model",
                    MODEL,
                    "--api-key-env",
                    "K",
                ),
                {},
                "--api-key-env",
            ),
            (
                (
                    "--author-provider",
                    "xai",
                    "--author-model",
                    MODEL,
                    "--api-key-env",
                    "a b",
                ),
                {},
                "--api-key-env",
            ),
        ]
        for index, (flags, env, expected) in enumerate(cases):
            with self.subTest(flags=flags, env=env):
                run, result = self.fresh(f"bad{index}", "--ordinary", *flags, env=env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertFalse(run.exists())
                self.assertFalse(self.marker.exists())
        self.assertEqual(sorted(p.name for p in self.path.iterdir()), ["game root"])

    def test_flags_and_environment_are_recorded_with_precedence(self):
        run, result = self.fresh(
            "flags",
            "--ordinary",
            "--author-provider",
            "xai-oauth",
            "--author-model",
            MODEL,
            env={
                "NYARLATHACK_AUTHOR_PROVIDER": "xai",
                "NYARLATHACK_AUTHOR_MODEL": "env-model",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        choice = self.choice(run)
        # Slice 3a: startup records what it found. No Hermes login and no
        # validator here, so this game runs without model content.
        self.assertEqual(choice["v"], 8)
        self.assertEqual(choice["authoring"], "no_model")
        self.assertIn("model authoring unavailable", result.stderr)
        self.assertFalse((run / "curio-lane.json").exists())
        self.assertEqual(
            choice["author"], dict(provider="xai-oauth", model=MODEL, key_env=None)
        )
        run, result = self.fresh(
            "env",
            "--ordinary",
            env={
                "NYARLATHACK_AUTHOR_PROVIDER": "xai",
                "NYARLATHACK_AUTHOR_MODEL": "env-model",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.choice(run)["author"],
            dict(provider="xai", model="env-model", key_env="XAI_API_KEY"),
        )
        run, result = self.fresh(
            "override",
            "--ordinary",
            "--author-provider",
            "xai",
            "--author-model",
            MODEL,
            "--api-key-env",
            "MY_XAI_KEY",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.choice(run)["author"]["key_env"], "MY_XAI_KEY")

    def test_restore_follows_the_record_not_the_environment(self):
        run, result = self.fresh(
            "recorded",
            "--ordinary",
            "--author-provider",
            "xai-oauth",
            "--author-model",
            MODEL,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = (run / "ordinary-choice.json").read_bytes()
        # The environment changed since: restore ignores it.
        result = self.run_cli(
            "--ordinary",
            "--reuse-run-dir",
            str(run),
            env={
                "NYARLATHACK_AUTHOR_PROVIDER": "xai",
                "NYARLATHACK_AUTHOR_MODEL": "other",
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((run / "ordinary-choice.json").read_bytes(), record)
        # Matching explicit flags are fine; contradicting ones fail closed.
        result = self.run_cli(
            "--ordinary",
            "--author-provider",
            "xai-oauth",
            "--author-model",
            MODEL,
            "--reuse-run-dir",
            str(run),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for flags in (
            ("--author-provider", "xai", "--author-model", MODEL),
            ("--author-provider", "xai-oauth", "--author-model", "other"),
        ):
            with self.subTest(flags=flags):
                result = self.run_cli("--ordinary", *flags, "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())

    def test_restore_of_unconfigured_run_refuses_new_authoring_flags(self):
        run, result = self.fresh("plain", "--ordinary")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli(
            "--ordinary",
            "--author-provider",
            "xai-oauth",
            "--author-model",
            MODEL,
            "--reuse-run-dir",
            str(run),
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.marker.exists())

    def test_authoring_flags_need_ordinary_play(self):
        run, result = self.fresh(
            "nonordinary", "--author-provider", "xai-oauth", "--author-model", MODEL
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(run.exists())

    def test_invalid_v7_records_fail_closed_on_restore(self):
        run, result = self.fresh(
            "tampered",
            "--ordinary",
            "--author-provider",
            "xai",
            "--author-model",
            MODEL,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        target = run / "ordinary-choice.json"
        good = json.loads(target.read_text())
        for author in (
            None,
            dict(provider="xai", model=MODEL, key_env="not a name"),
            dict(provider="xai-oauth", model=MODEL, key_env="XAI_API_KEY"),
            dict(provider="other", model=MODEL, key_env=None),
            dict(provider="xai", model=MODEL),
        ):
            with self.subTest(author=author):
                target.write_text(json.dumps(dict(good, author=author)))
                result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())
        # A v6 record may not carry an author field; a v7 none of authoring.
        for version in (6, 7):
            with self.subTest(version=version):
                target.write_text(json.dumps(dict(good, v=version)))
                result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
        for state in ("maybe", None, True):
            with self.subTest(authoring=state):
                target.write_text(json.dumps(dict(good, authoring=state)))
                result = self.run_cli("--ordinary", "--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_no_key_is_read_or_recorded_by_the_launcher(self):
        key = "t" + os.urandom(24).hex()  # throwaway, this process only
        run, result = self.fresh(
            "keyed",
            "--ordinary",
            "--author-provider",
            "xai",
            "--author-model",
            MODEL,
            env={"XAI_API_KEY": key},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(key, result.stderr + result.stdout)
        for path in run.rglob("*"):
            if path.is_file():
                self.assertNotIn(key.encode(), path.read_bytes(), path.name)


if __name__ == "__main__":
    unittest.main()
