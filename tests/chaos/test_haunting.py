"""Real terminal haunting gates; enabled with the existing game-test switch."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from gameplay_support import Game, ROOT


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class HauntingTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            (ROOT / "src/chaos_haunt.c").exists(), "haunting integration missing"
        )
        self.tmp = Path(tempfile.mkdtemp(prefix="nyarl-haunting-test-"))
        print("HAUNTING_ARTIFACTS=" + str(self.tmp), flush=True)
        self.clock = self.tmp / "clock.so"
        subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(self.clock),
            ],
            check=True,
        )

    def game(self, name, source, echoes=True):
        g = Game(
            ROOT / "dnethackdir",
            self.clock,
            wizard=True,
            root=self.tmp / name,
            echoes=echoes,
        )
        p = g.run / "haunting.lua"
        p.write_text(source)
        p.chmod(0o600)
        self.addCleanup(g.close)
        g.start()
        g.sanity(60)
        return g

    def walk(self, g):
        for char in "lhlhjkjklhlh":
            g.more(g.send(char))
            if (g.run / "dreamlands.json").exists():
                return
        self.fail("no shadow report: " + repr(g.events()))

    def test_handwritten_haunting_shadow_and_restore(self):
        source = (ROOT / "chaos/packs/footsteps.lua").read_text()
        g = self.game("haunt", source)
        self.walk(g)
        r = json.loads((g.run / "dreamlands.json").read_text())
        self.assertEqual(r["sandboxed"], 1, r)
        self.assertEqual(r["accepted"], 1, r)
        self.assertTrue(
            any(
                e["event"] == "haunting" and e["detail"] == "accepted"
                for e in g.events()
            )
        )
        self.assertEqual(g.save(), 0)
        g.start()
        g.wait_turns(3)
        self.assertEqual(g.quit(), 0)
        self.assertEqual(
            sum(
                e["event"] == "haunting" and e["detail"] == "accepted"
                for e in g.events()
            ),
            1,
        )

    def test_restore_without_run_directory_preserves_play(self):
        source = (ROOT / "chaos/packs/footsteps.lua").read_text()
        games = []
        for name, observe in (("restore-dir", True), ("restore-nodir", False)):
            g = self.game(name, source)
            self.walk(g)
            self.assertEqual(g.save(), 0)
            g.observe = observe
            g.start()
            for key in "lhlh.....":
                g.more(g.send(key))
            self.assertEqual(g.quit(), 0)
            games.append(g)
        self.assertEqual(games[0].inputs, games[1].inputs)
        self.assertEqual(games[0].raw, games[1].raw)
        self.assertEqual(
            (games[0].game / "xlogfile").read_bytes(),
            (games[1].game / "xlogfile").read_bytes(),
        )

    def test_generated_candidate_exact_source_and_replay(self):
        import hashlib

        source = (ROOT / "chaos/packs/luna-footsteps.lua").read_bytes()
        provenance = json.loads(
            (ROOT / "docs/evidence/milestone2-luna-generation.json").read_text()
        )
        self.assertEqual(
            hashlib.sha256(source).hexdigest(), provenance["source_sha256"]
        )
        games = []
        for name in ("generated-a", "generated-b"):
            g = self.game(name, source.decode())
            self.walk(g)
            report = json.loads((g.run / "dreamlands.json").read_text())
            self.assertEqual(report["accepted"], 1, report)
            self.assertEqual((g.run / "haunting-used.lua").read_bytes(), source)
            g.wait_turns(2)
            self.assertEqual(g.quit(), 0)
            games.append(g)
        self.assertEqual(games[0].inputs, games[1].inputs)
        self.assertEqual(games[0].raw, games[1].raw)
        self.assertEqual(games[0].events(), games[1].events())
        self.assertEqual(
            (games[0].game / "xlogfile").read_bytes(),
            (games[1].game / "xlogfile").read_bytes(),
        )

    def test_invalid_source_cannot_poison_player_save(self):
        for name, source in (("oversize", "x" * 4097), ("nul-source", "return 1\x00")):
            g = self.game(name, source)
            for char in "lhlhjkjk":
                g.more(g.send(char))
            self.assertEqual(g.save(), 0)
            g.start()
            self.assertTrue(
                any(
                    e["event"] == "session" and e["detail"] == "restore"
                    for e in g.events()
                )
            )
            self.assertEqual(g.quit(), 0)

    def test_rejected_shadow_echo_has_no_gameplay_effect(self):
        games = []
        source = "return function(c) while true do end end"
        for name, echoes in [("echo-on", True), ("echo-off", False)]:
            g = self.game(name, source, echoes)
            self.walk(g)
            r = json.loads((g.run / "dreamlands.json").read_text())
            self.assertEqual(r["accepted"], 0, r)
            self.assertGreater(r["script_errors"], 0, r)
            for _ in range(12):
                g.more(g.send("\x10"))
            self.assertEqual(g.quit(), 0)
            games.append(g)
        self.assertIn(b"refuses to take shape", games[0].raw)
        self.assertNotIn(b"refuses to take shape", games[1].raw)
        self.assertEqual(games[0].inputs, games[1].inputs)
        self.assertEqual(
            (games[0].game / "xlogfile").read_bytes(),
            (games[1].game / "xlogfile").read_bytes(),
        )
        self.assertEqual(games[0].events(), games[1].events())
