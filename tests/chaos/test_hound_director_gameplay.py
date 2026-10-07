"""Slice 5a Tier A: the hound lane in a real game, then its replay.

Record: a real wizard-mode game under the deterministic test clock, with no
haunting.lua at start (a model is configured). The director's HoundLane is
fed the engine's own events between keys. At the first public backtrack it
requests once (fake transport through the product path, provider xai-oauth),
then publishes haunting.lua by rename. The engine, not the director, decides
when it looks: its first haunting event names the window (turn, seq) of that
look. After the game, record_admission binds the window and the bytes.

Replay: a fresh game, no transport (patched to raise). stage_replay writes
the logged source and the window BEFORE the game starts, so the candidate is
present from turn 1, before the first backtrack; the engine must still look
only in the recorded window ("not yet"), and then exactly there ("exactly
then"). Events, the screen byte stream, inputs, haunting-used.lua and the
xlogfile must be byte-identical to the record.

Control: the same staged source without the binding (haunting-due removed).
The engine then looks as soon as a backtrack qualifies, earlier than the
record, so the binding is what pins the replay.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gameplay_support import ROOT, Game

from chaos import hound_author, hound_director as lane_mod, xai
from chaos.author_config import resolve
from test_curio_grounding import MODEL, FakeClient
from test_hound_director import SOURCE, FakePrecheck, envelope

WALK = "lhlhjkjklhlhjkjklhlh"


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class HoundDirectorGameplayTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-hound-director-"))
        os.chmod(self.artifacts, 0o700)
        print("HOUND_DIRECTOR_ARTIFACTS=" + str(self.artifacts), flush=True)
        self.clock = self.artifacts / "clock.so"
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

    def game(self, name):
        game = Game(
            ROOT / "dnethackdir", self.clock, wizard=True, root=self.artifacts / name
        )
        self.addCleanup(game.close)
        return game

    def play(self, game, after_key=lambda: None):
        game.start()
        game.sanity(60)
        for key in WALK:
            game.more(game.send(key))
            after_key()
        game.wait_turns(2)
        self.assertEqual(game.quit(), 0)

    @staticmethod
    def haunting(game):
        return [e for e in game.events() if e["event"] == "haunting"]

    def test_lane_publishes_engine_looks_once_and_replay_is_window_bound(self):
        record = self.game("record")
        ledger = xai.XaiLedger(self.artifacts / "ledger" / "xai-ledger.jsonl")
        lane_mod.new_lane(record.run, game="cd" * 16, seed=4242)
        backend = hound_author.build_backend(
            resolve("xai-oauth", MODEL),
            ledger=ledger,
            run_id="placeholder",  # the lane sets its recorded game id
            client_factory=lambda: (FakeClient(envelope()), MODEL),
        )
        lane = lane_mod.HoundLane(record.run, backend, validator=FakePrecheck())
        seen = {"offset": 0}
        states = []
        published_at = {}

        def feed():
            events = record.events()
            for e in events[seen["offset"] :]:
                lane.note(e)
            seen["offset"] = len(events)
            if lane.state in ("published", "fallback"):
                return
            state = lane.poll(safe=events[-1]["safe"] if events else None)
            if state == "requested":
                states.append(state)
                lane.wait(60)
                state = lane.poll(safe=events[-1]["safe"])
            if state != "idle":
                states.append(state)
                published_at.update(turn=events[-1]["turn"], seq=events[-1]["seq"])

        self.play(record, feed)
        self.assertEqual(states, ["requested", "published"])
        self.assertEqual(sum(r["status"] == "reserved" for r in ledger.rows()), 1)
        self.assertEqual({r["surface"] for r in ledger.rows()}, {"haunt"})
        self.assertEqual({r["run_id"] for r in ledger.rows()}, {"cd" * 16})
        backtracks = [e for e in record.events() if e["event"] == "backtrack"]
        self.assertTrue(backtracks)
        # The request came after the first public backtrack, never before.
        self.assertGreaterEqual(published_at["seq"], backtracks[0]["seq"])
        rows = self.haunting(record)
        self.assertTrue(rows, record.events())
        first = rows[0]
        # The engine looked only after publication.
        self.assertGreater(first["seq"], published_at["seq"])
        self.assertEqual(
            [r["detail"] for r in rows][:2], ["pre_admitted", "accepted"], rows
        )
        self.assertEqual(
            (record.run / "haunting-used.lua").read_bytes(), SOURCE.encode()
        )
        admission = lane_mod.record_admission(record.run)
        self.assertEqual(
            (admission["turn"], admission["seq"]), (first["turn"], first["seq"])
        )
        self.assertEqual(admission["evidence"], "haunt-evidence")

        # Replay: staged before start, no transport anywhere.
        replay = self.game("replay")
        with (
            patch.object(xai.XaiBackend, "generate", side_effect=AssertionError),
            patch.object(hound_author, "author_hound", side_effect=AssertionError),
            patch.object(hound_author, "build_backend", side_effect=AssertionError),
        ):
            self.assertEqual(lane_mod.stage_replay(replay.run, record.run), admission)
            self.assertTrue((replay.run / "haunting.lua").exists())
            self.play(replay)
        verified = lane_mod.verify_replay(replay.run, record.run)
        self.assertEqual(
            (verified["turn"], verified["seq"]), (first["turn"], first["seq"])
        )
        self.assertEqual(replay.inputs, record.inputs)
        self.assertEqual(bytes(replay.raw), bytes(record.raw))
        for name in ("events.jsonl", "haunting-used.lua", "dreamlands.json"):
            self.assertEqual(
                (record.run / name).read_bytes(), (replay.run / name).read_bytes(), name
            )
        self.assertEqual(
            (record.game / "xlogfile").read_bytes(),
            (replay.game / "xlogfile").read_bytes(),
        )

        # Control: the same bytes present from the start without the binding
        # are looked at earlier. The window file is what pins the replay.
        unbound = self.game("unbound")
        lane_mod.stage_replay(unbound.run, record.run)
        os.unlink(unbound.run / "haunting-due")
        self.play(unbound)
        early = self.haunting(unbound)[0]
        # A window is (turn, next seq); quiet turns share a seq, so compare both.
        self.assertLess((early["turn"], early["seq"]), (first["turn"], first["seq"]))
        self.assertNotEqual(
            (unbound.run / "events.jsonl").read_bytes(),
            (record.run / "events.jsonl").read_bytes(),
        )
        (self.artifacts / "equivalence.json").write_text(
            json.dumps(
                dict(
                    lane_states=states,
                    first_backtrack=dict(
                        turn=backtracks[0]["turn"], seq=backtracks[0]["seq"]
                    ),
                    published_after=published_at,
                    engine_window=dict(turn=first["turn"], seq=first["seq"]),
                    unbound_window=dict(turn=early["turn"], seq=early["seq"]),
                    haunting=[r["detail"] for r in rows],
                    inputs=len(record.inputs),
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    unittest.main()
