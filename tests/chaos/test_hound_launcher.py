"""Slice 5a launcher wiring with a real fake-game process (no engine, no
provider): which hound the game starts with.

- No model configured: footsteps.lua is installed before the game starts,
  exactly as on main, and there is no hound lane.
- An xAI provider live: nothing is installed at start; haunt-lane.json exists
  and the director's lane publishes later (model source or footsteps).
- An explicit --haunt PACK, a non-xAI provider, or a hound backend that
  cannot be built: that pack (or footsteps) at start, no lane.
"""

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from chaos import curio_author, hound_author, xai
from chaos.__main__ import main
from chaos.haunt import DEFAULT_PACK
import test_launcher as launcher_fixture

MODEL = "grok-test-model"


class FakeBackend:
    def __init__(self, provider):
        self.config = NS(provider=provider, model=MODEL)
        self.run_id = None


class HoundLauncherTests(unittest.TestCase):
    info = launcher_fixture.LauncherTests.info
    assert_reaped = launcher_fixture.LauncherTests.assert_reaped

    def setUp(self):
        launcher_fixture.LauncherTests.setUp(self)
        self.game.write_text(
            launcher_fixture.GAME.replace(
                "pathlib.Path(os.environ['GAME_MARKER']).write_text(json.dumps(info))",
                "h = run / 'haunting.lua'\n"
                "info['haunting'] = h.read_bytes().hex() if h.exists() else None\n"
                "info['hound_lane'] = (run / 'haunt-lane.json').exists()\n"
                "pathlib.Path(os.environ['GAME_MARKER']).write_text(json.dumps(info))",
            )
        )
        for name in ("NYARLATHACK_AUTHOR_PROVIDER", "NYARLATHACK_AUTHOR_MODEL"):
            self.env.pop(name, None)
        self.validator = NS(library=Path("/nonexistent/curio-validator.so"))
        self.hound_builds = []

    def play(self, name, *args, provider=None, hound=True):
        run = self.path / name
        argv = ["play", "--game-root", str(self.root), "--run-dir", str(run)]
        argv += ["--ordinary", "--no-next-use", *args]
        if provider is not None:
            argv += ["--author-provider", provider, "--author-model", MODEL]

        def build_hound(config, **kwargs):
            self.hound_builds.append(config.provider)
            if hound is False:
                raise xai.NoModelReachable("fixture")
            return (
                FakeBackend(config.provider)
                if config.provider in hound_author.PROVIDERS
                else None
            )

        with (
            patch.dict(os.environ, self.env, clear=True),
            redirect_stderr(io.StringIO()),
            patch.object(
                curio_author,
                "build_backend",
                side_effect=lambda config, **k: FakeBackend(config.provider),
            ),
            patch("chaos.launcher._curio_validator", return_value=self.validator),
            patch.object(hound_author, "build_backend", side_effect=build_hound),
            patch.object(hound_author, "HoundValidator", side_effect=lambda lib: lib),
        ):
            status = main(argv)
        self.assertEqual(status, 0)
        info = self.info()
        self.assert_reaped(info)
        return run, info

    def choice(self, run):
        return json.loads((run / "ordinary-choice.json").read_text())

    def test_no_model_installs_footsteps_at_start(self):
        run, info = self.play("none")
        self.assertEqual(info["haunting"], DEFAULT_PACK.read_bytes().hex())
        self.assertFalse(info["hound_lane"])
        self.assertEqual(self.hound_builds, [])
        self.assertEqual(self.choice(run)["v"], 6)

    def test_xai_live_starts_without_a_candidate_and_with_a_lane(self):
        run, info = self.play("model", provider="xai-oauth")
        self.assertIsNone(info["haunting"])
        self.assertTrue(info["hound_lane"])
        self.assertEqual(self.hound_builds, ["xai-oauth"])
        lane = json.loads((run / "haunt-lane.json").read_text())
        curio = json.loads((run / "curio-lane.json").read_text())
        # One game identity: the hound's ledger rows carry the curio's game.
        self.assertEqual((lane["step"], lane["game"]), ("idle", curio["game"]))
        self.assertEqual(self.choice(run)["authoring"], "live")
        # The recorded choice still names the default pack: the fallback.
        self.assertEqual(self.choice(run)["haunt_pack"], str(DEFAULT_PACK))

    def test_explicit_pack_keeps_that_pack(self):
        pack = self.path / "pack.lua"
        pack.write_bytes(b"return function(c) return {dx=1,dy=0,state=0} end\n")
        run, info = self.play("pack", "--haunt", str(pack), provider="xai-oauth")
        self.assertEqual(info["haunting"], pack.read_bytes().hex())
        self.assertFalse(info["hound_lane"])

    def test_no_haunt_has_no_hound(self):
        run, info = self.play("off", "--no-haunt", provider="xai-oauth")
        self.assertIsNone(info["haunting"])
        self.assertFalse(info["hound_lane"])
        self.assertEqual(self.hound_builds, [])

    def test_non_xai_provider_keeps_footsteps(self):
        run, info = self.play("codex", provider="openai-codex")
        self.assertEqual(info["haunting"], DEFAULT_PACK.read_bytes().hex())
        self.assertFalse(info["hound_lane"])

    def test_unbuildable_hound_backend_keeps_footsteps(self):
        run, info = self.play("unreachable", provider="xai-oauth", hound=False)
        self.assertEqual(info["haunting"], DEFAULT_PACK.read_bytes().hex())
        self.assertFalse(info["hound_lane"])
        self.assertTrue((run / "curio-lane.json").exists())


if __name__ == "__main__":
    unittest.main()
