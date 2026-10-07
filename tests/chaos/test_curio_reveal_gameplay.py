"""The end-of-game reveal names the placed curio as the player saw it.

Real nonwizard native game, opt-in (NYARLATHACK_GAME_TESTS=1, CHAOS=1 build).
The handwritten offline fixture from test_curio_gameplay is admitted, placed
on DL2, then the game is SAVED across the placement and restored in a fresh
process. The reveal written at the end of the restored game (dumplog section
and reveal.json) must name the curio from the engine-held u.curio.name, which
the save carried; test_curio_restart_gameplay already checks the name bytes
in the saved record itself.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from gameplay_support import ANSI, ROOT, Game
from chaos.curio_store import install_saved_source, store_candidate
from test_curio_gameplay import DISCOVERY, NOTE, SOURCE

NAMED = b'    Effect: "Offline counter" was placed on a new level on turn '
GENERIC = b"Effect: a curio whistle was placed"


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioRevealGameplayTests(unittest.TestCase):
    def test_reveal_names_curio_after_save_restore_across_placement(self):
        self.assertEqual((ROOT / ".chaos-build").read_text().strip(), "1")
        root = Path(tempfile.mkdtemp(prefix="curio-reveal-name-"))
        print("CURIO_REVEAL_ARTIFACTS=" + str(root), flush=True)
        clock = root / "clock.so"
        built = subprocess.run(
            [
                "cc",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(ROOT / "tests/chaos/replay_clock.c"),
                "-ldl",
                "-o",
                str(clock),
            ],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        game = Game(ROOT / "dnethackdir", clock, wizard=False, root=root / "session")
        self.addCleanup(game.close)
        bundles = root / "bundles"
        bundles.mkdir(mode=0o700)
        candidate = store_candidate(
            bundles,
            json.dumps({"lua_source": SOURCE.decode(), "continuity_note": NOTE}),
        )
        install_saved_source(
            game.run, bundle_root=bundles, candidate_id=candidate.candidate_id
        )
        game.start()
        self.assertIn(b"An uncanny curio may appear on a later floor.", game.raw)
        for key in DISCOVERY:
            game.send(key)
        game.more(game.send(">"))
        placed = [
            e
            for e in game.events()
            if e["event"] == "curio" and e["detail"] == "placed"
        ]
        self.assertEqual(len(placed), 1)
        placed_turn = placed[0]["turn"]

        # Save across the placement; keep the native save before restore
        # consumes it, and show the record carries the name.
        self.assertEqual(game.save(), 0)
        saves = list((game.game / "save").iterdir())
        self.assertEqual(len(saves), 1)
        kept = root / "save-after-placement"
        shutil.copy2(saves[0], kept)
        self.assertIn(b"Offline counter\x00", kept.read_bytes())

        restored_from = len(game.raw)
        game.start()
        self.assertFalse(list((game.game / "save").iterdir()), "restore consumed save")
        restored = ANSI.sub(b"", bytes(game.raw[restored_from:]))
        self.assertIn(b"Restoring save file", restored)
        self.assertNotIn(b"An uncanny curio may appear", restored)
        self.assertEqual(game.quit(), 0)  # the reveal prompt is answered n

        dumps = sorted((game.game / "dumplog").iterdir())
        self.assertTrue(dumps)
        dump = dumps[-1].read_bytes()
        expected = NAMED + str(placed_turn).encode() + b"."
        self.assertIn(expected, dump)
        self.assertNotIn(GENERIC, dump)
        record = json.loads((game.run / "reveal.json").read_text())
        self.assertIn(
            expected.decode().strip(), [line.strip() for line in record["lines"]]
        )
        self.assertEqual(sum(s["wizard"] for s in game.sessions), 0)
        (root / "evidence.json").write_text(
            json.dumps(
                {
                    "placed_turn": placed_turn,
                    "reveal_line": expected.decode(),
                    "save_after_placement_sha256": hashlib.sha256(
                        kept.read_bytes()
                    ).hexdigest(),
                    "sessions": len(game.sessions),
                },
                indent=2,
            )
        )
