"""Slice 2b: a recorded curio game replays to identical events and state.

Record: a real game under the deterministic test clock. After the first safe
point the curio is authored through chaos.curio_author (fake transport returning
a handwritten envelope, so no model) and installed as the director would, with
the safe point recorded. A fixed key tape follows: the next safe point admits
it on arrival at level 2, the fresh level 3 places the whistle (mksobj(WHISTLE)), more moves
follow, then the game saves.

Replay: a fresh game, same clock and binary. CurioReplayBackend installs the
logged source at the logged safe point (never a transport), the same tape is
sent, the game saves. Events, the engine's curio-used.lua, the xlogfile and
the input tape must be byte-identical; the saves must be identical except the
game's process id (hackpid) and raw in-memory pointers dNetHack serialises.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from gameplay_support import ROOT, Game

from chaos import curio_author, curio_replay, xai
from chaos.author_config import resolve

SOURCE = (
    "return {name='Replay counter',"
    "inspect=function(c) return 'A plain counter with three stages.' end,"
    "apply=function(c) return {text='First stage.',state=1,sanity_delta=0} end}"
)
# Install lands after safe point N; the engine reads it at N+1 (arrival on
# level 2). The next fresh floor (level 3) generates and places the whistle.
TAPE = ["s", b"\x16", "2\n", b"\x16", "3\n"] + list("hjklyubn") + ["s"] * 4
MODEL = "grok-test-model"  # fixture id


class Validator:
    """Engine admission in the game itself is the authority in this test."""

    library_sha256 = "0" * 64

    def validate(self, source, sanity, insight):
        return dict(
            admitted=True,
            failure=None,
            name="Replay counter",
            admission_inspect="A plain counter with three stages.",
            admission_apply=dict(text="First stage.", state=1, sanity_delta=0),
            grid_calls=2,
            grid_failures=0,
            inspect_texts=["A plain counter with three stages."],
            apply_texts=["First stage."],
        )


def fake_client():
    content = json.dumps({"lua_source": SOURCE, "continuity_note": "fixture"})
    return NS(
        base_url=xai.XAI_BASE_URL,
        chat=NS(
            completions=NS(
                create=lambda **k: NS(
                    model=MODEL,
                    choices=[NS(message=NS(content=content, tool_calls=None))],
                    usage=NS(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                )
            )
        ),
        close=lambda: None,
    )


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pointer(blob, i):
    """Is byte i inside an 8-byte little-endian user-space address?"""
    for start in range(max(0, i - 7), i + 1):
        value = int.from_bytes(blob[start : start + 8], "little")
        if 0x500000000000 <= value < 0x800000000000:
            return True
    return False


def save_differences(a, b, pids):
    """Byte runs where two equal-length saves differ, excluding the game's
    process id (hackpid, written per level) and in-memory pointers that
    dNetHack serialises raw (ASLR). Anything else is a state difference."""
    if len(a) != len(b):
        return [("length", len(a), len(b))]
    pid_a, pid_b = (p.to_bytes(4, "little") for p in pids)
    left = []
    i = 0
    while i < len(a):
        if a[i] == b[i]:
            i += 1
            continue
        start = i
        while i < len(a) and a[i] != b[i]:
            i += 1
        # Level records are packed, so hackpid copies need not be aligned.
        if any(
            a[s : s + 4] == pid_a and b[s : s + 4] == pid_b and i <= s + 4
            for s in range(max(0, start - 3), start + 1)
        ):
            continue
        if _pointer(a, start) and _pointer(b, start):
            continue
        left.append((start, a[start:i].hex(), b[start:i].hex()))
    return left


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioReplayGameplayTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = Path(tempfile.mkdtemp(prefix="nyarl-curio-replay-"))
        os.chmod(self.artifacts, 0o700)
        print("CURIO_REPLAY_ARTIFACTS=" + str(self.artifacts), flush=True)
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

    def play(self, game, before_tape):
        game.start()
        # The dnethack process reading the terminal (the launcher may sit
        # above it); its pid is the save's hackpid.
        self.pids.append(game._reader_pid)
        self.assertIsNotNone(game._reader_pid)
        latest = max(e["safe"] for e in game.events())
        before_tape(latest)
        for key in TAPE:
            game.more(game.send(key))
        self.assertEqual(game.save(), 0)
        saves = sorted((game.game / "save").iterdir())
        self.assertEqual(len(saves), 1)
        return saves[0]

    def test_recorded_curio_game_replays_identically(self):
        self.pids = []
        record = self.game("record")
        evidence = self.artifacts / "evidence"
        ledger = xai.XaiLedger(self.artifacts / "ledger" / "xai-ledger.jsonl")

        def author_and_install(latest):
            backend = curio_author.build_backend(
                resolve("xai-oauth", MODEL),
                ledger=ledger,
                run_id="record",
                client_factory=lambda: (fake_client(), MODEL),
            )
            receipt = curio_author.author_curio(
                backend,
                events_dir=record.run,
                evidence_dir=evidence,
                game_seed=1234567,
                validator=Validator(),
            )
            self.assertEqual(receipt["outcome"], "ready")
            curio_author.install(record.run, evidence, safe=latest)

        record_save = self.play(record, author_and_install)

        replay_game = self.game("replay")
        backend = curio_replay.CurioReplayBackend(evidence)

        def replay_install(latest):
            self.assertTrue(backend.due(latest))
            backend.install(replay_game.run)

        with (
            patch.object(xai.XaiBackend, "generate", side_effect=AssertionError),
            patch.object(curio_author, "author_curio", side_effect=AssertionError),
        ):
            replay_save = self.play(replay_game, replay_install)

        events = record.events()
        curio_rows = [e["detail"] for e in events if e["event"] == "curio"]
        self.assertIn("admitted", curio_rows)
        self.assertIn("placed", curio_rows)
        self.assertEqual((record.run / "curio-used.lua").read_bytes(), SOURCE.encode())
        backend.verify(replay_game.run)  # engine's curio-used.lua cross-check
        self.assertEqual(replay_game.inputs, record.inputs)
        for name in ("events.jsonl", "curio-used.lua", "curio.lua"):
            self.assertEqual(
                (record.run / name).read_bytes(),
                (replay_game.run / name).read_bytes(),
                name,
            )
        self.assertEqual(record_save.name, replay_save.name)
        # Same final state: the saves differ only in hackpid and raw pointers.
        record_bytes, replay_bytes = record_save.read_bytes(), replay_save.read_bytes()
        self.assertEqual(
            save_differences(record_bytes, replay_bytes, self.pids), [], "final save"
        )
        self.assertEqual(
            (record.game / "xlogfile").read_bytes(),
            (replay_game.game / "xlogfile").read_bytes(),
        )
        (self.artifacts / "equivalence.json").write_text(
            json.dumps(
                dict(
                    curio_rows=curio_rows,
                    events_sha256=digest(record.run / "events.jsonl"),
                    record_save_sha256=digest(record_save),
                    replay_save_sha256=digest(replay_save),
                    save_bytes=len(record_bytes),
                    save_state_differences=0,
                    hackpids=self.pids,
                    install=curio_author.read_install(evidence),
                    inputs=len(record.inputs),
                ),
                indent=2,
            )
        )


if __name__ == "__main__":
    unittest.main()
