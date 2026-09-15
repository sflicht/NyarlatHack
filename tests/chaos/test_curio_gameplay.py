"""Task 8a: handwritten bundle -> real ordinary stair travel -> native use.

One declared clock/entropy fixture, no seed search. The fixed input sequence was
obtained by exploring only the rendered PTY (pyte during the exploratory probe),
not hidden map/curio coordinates. Replay has no pyte dependency. Includes bumps,
ordinary combat, autopickup and UI paging, not an optimized or general navigator.
No injected player/curio state, wizard commands, director, or engine wrappers.
This is standalone bundle preflight + direct native exec, NOT launcher acceptance.
Save/restore, both UI modes and record snapshots remain later Task 8 slices.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from gameplay_support import ANSI, ROOT, Game
from chaos import curio_continuity as continuity
from chaos.curio_store import install_saved_source, store_candidate

SOURCE = b"""return {name='Offline counter',inspect=function(c) return 'A plain counter with three stages.' end,apply=function(c)
if c.state==0 then return {text='First stage.',state=1,sanity_delta=-2}
elseif c.state==1 then return {text='Second stage.',state=2,sanity_delta=1}
else return {text='Third stage.',state=3,sanity_delta=0} end end}
"""
NOTE = "Handwritten offline acceptance fixture; not model output."
# Starts after Game.start()'s inheritance/paging. Spaces are observed --More--.
DISCOVERY = "\x12hhkkkkkkkkkllllllllllykukkhhhhllljjjnljjnllkkukklllkklllkkllllllllllllllllllllllllllkjjjlllllllllllkkkhjjhkkhjjhkkhjjhkkhjjhkkhjjjjllllllllhhhbjllllllhhhhhbjjjllllllhhhjjhjjjkjllljj jhhkkljhhkjjhhhhkjlulkkkkkykhhhhhhkkkklllhhhhhkkhhjjhhjjhhjjlllllllnjjjjhhkjjkyklkkhjhkhjjljhhkkkhjjjhkkkhjjjhkkyhkkllhhhhhhjjljlnjllyubybhyjhkkhjhjljhhkkhjjhkkhjjhkkllllllluykkhhkkkkklllllkhhhhhkbhjhkhjhkhjhkhjhkybbhhhhhhkhjh  j n  j hjllbjj hkkjjnjbhylukkkulluuluullllllllllllllllllllllllnnlllllllllnhhhhbnllllllllnkjlljjllllllnjjnn"


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioGameplayTests(unittest.TestCase):
    def test_task8a_bundle_ordinary_stairs_inspect_three_uses_continuity(self):
        self.assertEqual((ROOT / ".chaos-build").read_text().strip(), "1")
        root = Path(tempfile.mkdtemp(prefix="curio8a-green-"))
        print("CURIO8A_ARTIFACTS=" + str(root), flush=True)
        inputs = [
            Path(__file__),
            ROOT / "tests/chaos/gameplay_support.py",
            ROOT / "tests/chaos/replay_clock.c",
        ]
        (root / "fixture-inputs.json").write_text(
            json.dumps(
                {
                    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in inputs
                },
                indent=2,
            )
        )
        for path in inputs:
            (root / path.name).write_bytes(path.read_bytes())
        clock = root / "clock.so"
        command = [
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
        ]
        (root / "build-command.json").write_text(json.dumps(command))
        built = subprocess.run(command, capture_output=True, timeout=30)
        (root / "build.log").write_bytes(built.stdout + built.stderr)
        self.assertEqual(built.returncode, 0, built.stderr)
        game = Game(ROOT / "dnethackdir", clock, wizard=False, root=root / "session")
        self.addCleanup(game.close)
        bundles, journal = root / "bundles", root / "journal"
        bundles.mkdir(mode=0o700)
        journal.mkdir(mode=0o700)
        continuity.create_journal(journal)
        candidate = store_candidate(
            bundles,
            json.dumps(
                {
                    "lua_source": SOURCE.decode(),
                    "continuity_note": NOTE,
                }
            ),
        )
        self.assertEqual(candidate.candidate_id, hashlib.sha256(SOURCE).hexdigest())
        continuity.register(journal, bundles, candidate.candidate_id)
        self.assertEqual(continuity.prior_notes(journal)[0]["status"], "authored")
        receipt = install_saved_source(
            game.run,
            bundle_root=bundles,
            candidate_id=candidate.candidate_id,
        )
        continuity.bind_run(journal, candidate.candidate_id, game.run)
        self.assertEqual(continuity.prior_notes(journal)[0]["status"], "installed")
        self.assertEqual(
            install_saved_source(
                game.run,
                bundle_root=bundles,
                candidate_id=candidate.candidate_id,
                mode="verify",
            ),
            receipt,
        )
        self.assertFalse((game.run / "events.jsonl").exists())
        game.start()
        events = game.events()
        self.assertEqual(events[0]["detail"], "new")
        curio = [e for e in events if e["event"] == "curio"]
        self.assertEqual([e["detail"] for e in curio], ["pre_admitted", "admitted"])
        self.assertEqual([e["sanity"] for e in curio], [100, 100])
        self.assertEqual([e["spent"] for e in curio], [0, 1])
        self.assertIn(b"An uncanny curio may appear on a later floor.", game.raw)
        # Exact observed inputs; do not silently skip/retry prompts or seed-reroll.
        for key in DISCOVERY:
            game.send(key)
        game.save_artifacts()
        before_stairs = len(game.raw)
        game.more(game.send(">"))
        self.assertIn(b"Dlvl:2", bytes(game.raw[before_stairs:]))
        curio = [e for e in game.events() if e["event"] == "curio"]
        self.assertEqual(
            [e["detail"] for e in curio], ["pre_admitted", "admitted", "placed"]
        )
        self.assertEqual(curio[-1]["spent"], 1)
        # Visible nearby tool glyph. Ordinary burden prevents the first step;
        # inspect inventory and drop the autopicked chest through native UI.
        game.more(game.send("y"))
        game.send(",")
        game.send("i")
        self.assertIn(b"q - a chest", game.send(" "))
        game.send(b"\x1b")
        self.assertIn(b"You drop a chest", game.send("dq"))
        self.assertIn(b"s - an Offline counter", game.more(game.send("y")))
        game.send(",")
        inspect_start = len(game.raw)
        game.send("i")
        self.assertIn(b"s - an Offline counter", game.send(" "))
        menu = game.send("s")
        self.assertIn(b"I - Describe this item", menu)
        self.assertIn(b"a - Apply", menu)
        self.assertIn(b"A plain counter with three stages.", game.send("I"))
        game.more(game.send(" "))
        inspection = bytes(game.raw[inspect_start:])
        self.assertNotIn(b"whistle", inspection.lower())
        (root / "inspection.raw").write_bytes(inspection)
        self.assertIn(b"T:575", ANSI.sub(b"", inspection))
        for stage, turn in zip(
            (b"First stage.", b"Second stage.", b"Third stage."), (576, 577, 578)
        ):
            output = game.more(game.send("as"))
            self.assertIn(stage, output)
            self.assertIn(f"T:{turn}".encode(), output)
        inert = game.more(game.send("as"))
        self.assertIn(b"This curio is inert.", inert)
        self.assertIn(b"T:578", inert)
        self.assertNotIn(b"T:579", inert)
        applied = [
            e
            for e in game.events()
            if e["event"] == "curio" and e["detail"].startswith("applied ")
        ]
        self.assertEqual(
            [e["detail"] for e in applied],
            [
                "applied requested=-2 actual=-2",
                "applied requested=1 actual=1",
                "applied requested=0 actual=0",
            ],
        )
        self.assertEqual([e["sanity"] for e in applied], [98, 99, 99])
        self.assertEqual([e["turn"] for e in applied], [575, 576, 577])
        # Native status shows successful full turns and no fourth turn on inert use.
        plain = ANSI.sub(b"", bytes(game.raw))
        self.assertIn(b"T:578", plain)
        self.assertEqual(game.quit(), 0)
        native_events = (game.run / "events.jsonl").read_bytes()
        self.assertEqual((game.run / "curio.lua").read_bytes(), SOURCE)
        self.assertEqual((game.run / "curio-used.lua").read_bytes(), SOURCE)
        continuity.observe(journal, candidate.candidate_id)
        notes = continuity.prior_notes(journal)
        self.assertEqual(
            notes,
            [
                {
                    "candidate_id": candidate.candidate_id,
                    "status": "placed",
                    "continuity_note": NOTE,
                }
            ],
        )
        self.assertEqual((game.run / "events.jsonl").read_bytes(), native_events)
        # Placed is historical after quit; it does NOT assert current ownership.
        curio = [e for e in game.events() if e["event"] == "curio"]
        self.assertEqual(sum(e["detail"] == "placed" for e in curio), 1)
        self.assertTrue(all(e["spent"] == 1 for e in curio[1:]))
        inputs = b"".join(bytes.fromhex(s) for s in game.inputs)
        self.assertNotIn(b"setsanity", inputs)
        self.assertNotIn(b"\x16", inputs)
        self.assertFalse(game.sessions[0]["wizard"])
        (root / "evidence.json").write_text(
            json.dumps(
                {
                    "candidate_id": candidate.candidate_id,
                    "notes": notes,
                    "path": "standalone bundle install/verify then direct native exec",
                    "authorship": "handwritten offline fixture, not model output",
                    "discovery": "fixed PTY-visible exploration; one clock, no seed search",
                    "native_events_sha256": hashlib.sha256(native_events).hexdigest(),
                    "applied": applied,
                    "remaining": [
                        "launcher held-lock bundle preflight",
                        "direct UI mode",
                        "native record snapshots",
                        "save/restore",
                        "invalid program",
                    ],
                },
                indent=2,
            )
        )
