"""Slice 3a Tier A: the director lane in a real game, then its replay.

Record: a real wizard-mode game under the deterministic test clock. At the
first observed safe point N the director's CurioLane runs for real: durable
lane record, background authoring through the product path (configured
provider xai-oauth, a fake transport, no model), and publication of curio.lua
by write-temp-then-rename. The engine, not the director, decides when it is
admitted: it logs pre_admitted at the safe index of its own read (N+1, the
arrival on level 2). After the game, record_admission binds that index and the
SHA-256 of the engine's curio-used.lua into the evidence. install.json's
director-observed index (N) stays advisory.

Replay: a fresh game. stage_replay writes the logged source and the engine's
logged index (curio-safe) BEFORE the game starts, so the source is present at
safe point 1 already; the engine must still admit it only at the logged index.
No transport, no authoring: both are patched to raise. Events, curio-used.lua,
xlogfile and the input tape must be byte-identical, the saves identical except
hackpid and raw pointers, and verify_replay / CurioReplayBackend must agree.

Untriggered lane: a lane that is configured and polled every turn but whose
trigger is never met (turn < 150) leaves the game byte-identical to the
empty-mailbox game: the lane writes only curio-lane.json, which the engine
never reads.

The trigger thresholds themselves (150 turns, episodes or a seen whisper,
budget) are covered offline in test_curio_director.py; here trigger_ready is
forced so a short real game reaches the publish/admit/replay path.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gameplay_support import ROOT, Game
from test_curio_replay_gameplay import (
    MODEL,
    SOURCE,
    Validator,
    digest,
    fake_client,
    save_differences,
)

from chaos import curio_author, curio_director as lane_mod, curio_replay, xai
from chaos.author_config import resolve

# Lane publishes after safe N; the engine reads it at N+1 (arrival on level 2);
# level 3 places the whistle. Same tape as slice 2b's replay test.
TAPE = ["s", b"\x16", "2\n", b"\x16", "3\n"] + list("hjklyubn") + ["s"] * 4


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioDirectorGameplayTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-director-"))
        os.chmod(self.artifacts, 0o700)
        print("CURIO_DIRECTOR_ARTIFACTS=" + str(self.artifacts), flush=True)
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
        self.pids = []

    def game(self, name):
        game = Game(
            ROOT / "dnethackdir", self.clock, wizard=True, root=self.artifacts / name
        )
        self.addCleanup(game.close)
        return game

    def backend(self, ledger):
        return curio_author.build_backend(
            resolve("xai-oauth", MODEL),
            ledger=ledger,
            run_id="placeholder",  # the lane sets its recorded game id
            client_factory=lambda: (fake_client(), MODEL),
        )

    def play(self, game, before_tape=lambda latest: None, tape=TAPE):
        game.start()
        self.pids.append(game._reader_pid)
        latest = max(e["safe"] for e in game.events())
        before_tape(latest)
        for key in tape:
            game.more(game.send(key))
        self.assertEqual(game.save(), 0)
        saves = sorted((game.game / "save").iterdir())
        self.assertEqual(len(saves), 1)
        return saves[0], latest

    def test_lane_publishes_engine_admits_and_replay_is_engine_bound(self):
        record = self.game("record")
        ledger = xai.XaiLedger(self.artifacts / "ledger" / "xai-ledger.jsonl")
        lane_mod.new_lane(record.run, game="ab" * 16, seed=1234567)
        states = []

        def run_lane(latest):
            lane = lane_mod.CurioLane(
                record.run, self.backend(ledger), validator=Validator()
            )
            with patch.object(lane_mod, "trigger_ready", return_value=True):
                states.append(lane.poll(safe=latest))
                lane.wait(60)
                states.append(lane.poll(safe=latest))

        record_save, observed = self.play(record, run_lane)
        self.assertEqual(states, ["requested", "published"])
        self.assertEqual(
            sum(r["status"] == "reserved" for r in ledger.rows()), 1, "one send"
        )
        self.assertEqual(
            {r["run_id"] for r in ledger.rows()}, {"ab" * 16}, "ledger game id"
        )
        evidence = record.run / "curio-evidence"
        install = curio_author.read_install(evidence)
        admission = lane_mod.record_admission(record.run, evidence)
        # The engine's index is the authority; the director's is advisory.
        self.assertEqual(install["safe"], observed)
        self.assertEqual(admission["safe"], observed + 1)
        self.assertEqual(admission["source_sha256"], curio_author._sha(SOURCE.encode()))
        self.assertEqual(lane_mod.read_lane(record.run)["step"], "published")

        replay = self.game("replay")
        staged = lane_mod.stage_replay(replay.run, evidence)
        self.assertEqual(staged, admission)
        backend = curio_replay.CurioReplayBackend(evidence)
        with (
            patch.object(xai.XaiBackend, "generate", side_effect=AssertionError),
            patch.object(curio_author, "author_curio", side_effect=AssertionError),
            patch.object(curio_author, "build_backend", side_effect=AssertionError),
        ):
            replay_save, replay_first = self.play(replay)
        # Present from the start, yet not admitted before the logged index.
        self.assertLess(replay_first, admission["safe"])
        self.assertEqual(lane_mod.verify_replay(replay.run, evidence), admission)
        self.assertEqual(backend.verify_admission(replay.run), admission)
        # The 2b store verify() needs the store's install receipt; the lane
        # publishes by rename instead, so compare the engine's bytes directly.
        self.assertEqual(
            (replay.run / "curio-used.lua").read_bytes(),
            (evidence / "source.lua").read_bytes(),
        )

        rows = [e["detail"] for e in record.events() if e["event"] == "curio"]
        self.assertIn("admitted", rows)
        self.assertIn("placed", rows)
        self.assertEqual(replay.inputs, record.inputs)
        for name in ("events.jsonl", "curio-used.lua", "curio.lua"):
            self.assertEqual(
                (record.run / name).read_bytes(),
                (replay.run / name).read_bytes(),
                name,
            )
        self.assertEqual(record_save.name, replay_save.name)
        record_bytes, replay_bytes = record_save.read_bytes(), replay_save.read_bytes()
        self.assertEqual(
            save_differences(record_bytes, replay_bytes, self.pids), [], "final save"
        )
        self.assertEqual(
            (record.game / "xlogfile").read_bytes(),
            (replay.game / "xlogfile").read_bytes(),
        )
        (self.artifacts / "equivalence.json").write_text(
            json.dumps(
                dict(
                    lane_states=states,
                    curio_rows=rows,
                    director_observed_safe=observed,
                    engine_admission=admission,
                    replay_first_safe=replay_first,
                    events_sha256=digest(record.run / "events.jsonl"),
                    record_save_sha256=digest(record_save),
                    replay_save_sha256=digest(replay_save),
                    save_bytes=len(record_bytes),
                    save_state_differences=0,
                    hackpids=self.pids,
                    inputs=len(record.inputs),
                ),
                indent=2,
            )
        )

    def test_untriggered_lane_equals_empty_mailbox(self):
        tape = ["s"] * 6 + list("hjkl") + [b"\x16", "2\n"] + ["s"] * 3
        games = {}
        for name in ("empty", "lane-idle"):
            game = self.game(name)
            lane = None
            if name == "lane-idle":
                lane_mod.new_lane(game.run, seed=7)
                ledger = xai.XaiLedger(self.artifacts / "ledger-idle" / "l.jsonl")
                lane = lane_mod.CurioLane(
                    game.run, self.backend(ledger), validator=Validator()
                )
            game.start()
            for key in tape:
                game.more(game.send(key))
                if lane is not None:
                    latest = game.events()[-1]
                    self.assertEqual(
                        lane.poll(safe=latest["safe"], latest=latest), "idle"
                    )
            self.assertEqual(game.save(), 0)
            games[name] = game
        empty, idle = games["empty"], games["lane-idle"]
        self.assertEqual(idle.inputs, empty.inputs)
        self.assertEqual(idle.raw, empty.raw)
        self.assertEqual(
            (idle.run / "events.jsonl").read_bytes(),
            (empty.run / "events.jsonl").read_bytes(),
        )
        self.assertEqual(
            (idle.game / "xlogfile").read_bytes(),
            (empty.game / "xlogfile").read_bytes(),
        )
        self.assertFalse((idle.run / "curio.lua").exists())
        self.assertFalse(any(e["event"] == "curio" for e in idle.events()))
        self.assertEqual(
            sorted(p.name for p in idle.run.iterdir()),
            sorted([*(p.name for p in empty.run.iterdir()), "curio-lane.json"]),
        )


if __name__ == "__main__":
    unittest.main()
