"""Slice 5a offline: the director's hound lane. Fake transports, a fake
pre-check and an injected clock; no provider, no Hermes, no game.

What the player sees is decided by one thing the lane controls: which bytes
it publishes as haunting.lua, and when. With a model configured the engine
finds no candidate until the lane publishes one; then its own shadow trial
decides. So every case asserts what was published (the model's source, the
footsteps fallback, or nothing yet) and the lane's durable record.
"""

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from chaos import hound_author, hound_director as lane_mod, lane as shared, xai
from chaos.author_config import resolve
from chaos.haunt import DEFAULT_PACK

from test_curio_director import FakeClock
from test_curio_grounding import HISTORY, MODEL, FakeClient

SOURCE = (
    "return function(c)\n"
    "  local p = c.history[1]\n"
    "  local dx, dy = 0, 0\n"
    "  if p.x > c.mx then dx = 1 elseif p.x < c.mx then dx = -1 end\n"
    "  if p.y > c.my then dy = 1 elseif p.y < c.my then dy = -1 end\n"
    "  return {dx=dx, dy=dy, state=(c.state+1)%1000001}\n"
    "end\n"
)
FOOTSTEPS = DEFAULT_PACK.read_bytes()


def envelope(source=SOURCE):
    return json.dumps({"source": source})


class FakePrecheck:
    """Stands in for hound_author.HoundValidator (no native library)."""

    library_sha256 = "0" * 64

    def __init__(self, admitted=True):
        self.admitted = admitted
        self.calls = []

    def validate(self, source):
        self.calls.append(source)
        return dict(
            admitted=self.admitted,
            failure=None if self.admitted else "native_step",
            grid_calls=120,
            grid_failures=0 if self.admitted else 120,
            grid_moves=100 if self.admitted else 0,
            distinct_steps=5 if self.admitted else 0,
            library_sha256=self.library_sha256,
        )


def lines(path):
    return path.read_bytes().splitlines(keepends=True)


class HoundBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        os.chmod(self.root, 0o700)
        self.ledger = xai.XaiLedger(self.root / "ledger" / "xai-ledger.jsonl")
        self.config = resolve("xai-oauth", MODEL)
        self.rundir = self.root / ("run-" + uuid.uuid4().hex[:8])
        self.rundir.mkdir(mode=0o700)
        # The capture up to its first backtrack (seq 7), before any haunting.
        history = lines(HISTORY)
        first = next(
            i for i, line in enumerate(history) if b'"event":"backtrack"' in line
        )
        self.before = history[:first]
        self.backtrack = history[first]
        self.events(self.before)
        lane_mod.new_lane(self.rundir, seed=7)

    def events(self, rows):
        path = self.rundir / "events.jsonl"
        path.write_bytes(b"".join(rows))
        os.chmod(path, 0o600)

    def backtracked(self):
        self.events(self.before + [self.backtrack])

    def backend(self, content=None, create=None):
        client = FakeClient(envelope() if content is None else content)
        if create is not None:
            client.chat.completions.create = create
        self.client = client
        return hound_author.build_backend(
            self.config,
            ledger=self.ledger,
            run_id="placeholder",
            client_factory=lambda: (client, MODEL),
        )

    def lane(self, backend=None, validator=None, **kwargs):
        return lane_mod.HoundLane(
            self.rundir,
            self.backend() if backend is None else backend,
            validator=FakePrecheck() if validator is None else validator,
            **kwargs,
        )

    def drive(self, lane, safe=1, timeout=10):
        state = lane.poll(safe=safe)
        for _ in range(int(timeout / 0.05)):
            if state != "requested":
                break
            lane.wait(0.05)
            state = lane.poll(safe=safe)
        return state

    def candidate(self):
        path = self.rundir / "haunting.lua"
        return path.read_bytes() if path.exists() else None

    def sends(self):
        return sum(r["status"] == "reserved" for r in self.ledger.rows())

    def record(self):
        return lane_mod.read_lane(self.rundir)


class RequestTests(HoundBase):
    def test_no_request_before_the_first_backtrack(self):
        lane = self.lane()
        for _ in range(3):
            self.assertEqual(lane.poll(safe=1), "idle")
        self.assertTrue(lane.active)
        self.assertEqual((self.sends(), self.candidate()), (0, None))

    def test_request_at_the_first_backtrack_then_publish(self):
        lane = self.lane()
        self.assertEqual(lane.poll(safe=1), "idle")
        lane.note(json.loads(self.backtrack))
        self.assertEqual(self.drive(lane), "published")
        self.assertEqual(self.candidate(), SOURCE.encode())
        self.assertEqual(self.sends(), 1)
        self.assertEqual(
            {r["surface"] for r in self.ledger.rows()}, {"haunt"}, "ledger surface"
        )
        record = self.record()
        self.assertEqual(
            (record["step"], record["evidence"]), ("published", "haunt-evidence")
        )
        self.assertFalse(lane.active)

    def test_backtrack_already_in_the_log_requests_at_once(self):
        self.backtracked()
        self.assertEqual(self.drive(self.lane()), "published")
        self.assertEqual(self.sends(), 1)

    def test_lane_record_is_durable_before_the_send(self):
        seen = []
        client = FakeClient(envelope())
        original = client.create

        def create(**kwargs):
            seen.append(lane_mod.read_lane(self.rundir)["step"])
            return original(**kwargs)

        self.backtracked()
        self.assertEqual(
            self.drive(self.lane(self.backend(create=create))), "published"
        )
        self.assertEqual(seen, ["requested"])

    def test_one_request_per_game(self):
        self.backtracked()
        lane = self.lane()
        self.assertEqual(self.drive(lane), "published")
        for safe in (2, 3, 4):
            lane.note(json.loads(self.backtrack))
            self.assertEqual(lane.poll(safe=safe), "published")
        self.assertEqual(self.sends(), 1)

    def test_published_by_rename_with_one_link(self):
        self.backtracked()
        self.drive(self.lane())
        st = os.stat(self.rundir / "haunting.lua")
        self.assertEqual((st.st_nlink, st.st_mode & 0o777), (1, 0o600))
        self.assertEqual(
            sorted(p.name for p in self.rundir.iterdir() if p.name.startswith(".")), []
        )

    def test_engine_decision_first_means_no_request(self):
        # The engine looked at a candidate already (an older run, or the
        # footsteps fallback): the lane never asks.
        self.events(self.before + [self.backtrack] + lines(HISTORY)[11:12])
        lane = self.lane()
        self.assertEqual(lane.poll(safe=1), "idle")
        self.assertFalse(lane.active)
        self.assertEqual(self.sends(), 0)

    def test_prompt_is_the_free_design_ask_on_public_history(self):
        self.backtracked()
        self.drive(self.lane())
        prepared = json.loads(
            (self.rundir / "haunt-evidence" / "prompt.json").read_text()
        )
        self.assertIn("Design the pursuit yourself", prepared["instructions"])
        self.assertNotIn("three observations before", prepared["instructions"])
        self.assertIn("public_history", json.loads(prepared["prompt"]))
        self.assertIn("Literary influence", prepared["instructions"])
        self.assertEqual(prepared["layer"], hound_author.curio.seeded_layer(7))


class FallbackTests(HoundBase):
    """Every lane failure publishes footsteps.lua: the hound still happens."""

    def assert_fallback(self, lane, outcome, sends, error_type=None):
        self.backtracked()
        lane.note(json.loads(self.backtrack))  # as the director loop feeds it
        self.assertEqual(self.drive(lane), "fallback")
        self.assertEqual(self.candidate(), FOOTSTEPS)
        record = self.record()
        self.assertEqual(
            (record["step"], record["outcome"], record.get("error_type")),
            ("fallback", outcome, error_type),
        )
        self.assertEqual(self.sends(), sends)
        self.assertFalse(lane.active)

    def failing(self, status, error=None):
        class Failure(RuntimeError):
            status_code = status
            response = type("R", (), {"headers": {"Retry-After": "0"}})()

        def create(**kwargs):
            raise error or Failure("fixture")

        return self.backend(create=create)

    def test_transport(self):
        self.assert_fallback(self.lane(self.failing(502)), "transport_failed", 3)

    def test_transport_deadline(self):
        self.assert_fallback(
            self.lane(self.failing(None, error=TimeoutError())), "deadline", 1
        )

    def test_envelope_regenerates_once_then_falls_back(self):
        self.assert_fallback(
            self.lane(self.backend("not json")), "envelope_rejected", 2
        )
        self.assertTrue((self.rundir / "haunt-evidence-2" / "receipt.json").exists())

    def test_regeneration_only_for_envelope(self):
        self.assert_fallback(
            self.lane(validator=FakePrecheck(admitted=False)), "native_rejected", 1
        )

    def test_regeneration_can_succeed(self):
        replies = iter(["not json", envelope()])
        client = FakeClient(envelope())
        original = client.create

        def create(**kwargs):
            client.content = next(replies)
            return original(**kwargs)

        self.backtracked()
        self.assertEqual(
            self.drive(self.lane(self.backend(create=create))), "published"
        )
        self.assertEqual(self.record()["evidence"], "haunt-evidence-2")
        self.assertEqual(self.candidate(), SOURCE.encode())

    def test_envelope_shapes(self):
        for raw in (
            json.dumps({"source": SOURCE, "extra": 1}),
            json.dumps({"lua_source": SOURCE}),
            json.dumps({"source": ""}),
            json.dumps({"source": "x" * 4097}),
            json.dumps({"source": "return 1\u0000"}),
            json.dumps(["source"]),
            '{"source":"a","source":"b"}',
        ):
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(ValueError):
                    hound_author.parse_envelope(raw)
        self.assertEqual(hound_author.parse_envelope(envelope()), SOURCE.encode())

    def test_no_model_at_startup_publishes_footsteps_at_once(self):
        lane = lane_mod.HoundLane(self.rundir, None, validator=FakePrecheck())
        self.assertEqual(lane.state, "no_model")
        self.assertEqual(self.candidate(), FOOTSTEPS)
        self.assertFalse(lane.active)


class LaneClockTests(HoundBase):
    """The deadline is the lane's own clock; the transport is gated by
    events, never by real sleeps."""

    def gated(self):
        self.release = threading.Event()
        self.entered = threading.Event()
        client = FakeClient(envelope())
        original = client.create

        def create(**kwargs):
            self.entered.set()
            assert self.release.wait(10), "test never released the send"
            return original(**kwargs)

        return self.backend(create=create)

    def hung(self):
        self.backtracked()
        self.clock = FakeClock()
        lane = self.lane(self.gated(), clock=self.clock)
        self.assertEqual(lane.poll(safe=1), "requested")
        self.assertTrue(self.entered.wait(10))
        self.clock.advance(hound_author.DEADLINE_S - 1)
        self.assertEqual(lane.poll(safe=2), "requested")
        self.assertIsNone(self.candidate())
        self.clock.advance(1)
        self.assertEqual(lane.poll(safe=3), "fallback")
        return lane

    def test_hang_past_the_deadline_falls_back(self):
        lane = self.hung()
        self.assertTrue(lane.thread.is_alive())
        self.assertEqual(self.candidate(), FOOTSTEPS)
        record = self.record()
        self.assertEqual(
            (record["step"], record["outcome"], record["error_type"]),
            ("fallback", "deadline", shared.LANE_DEADLINE),
        )
        self.release.set()
        lane.wait(10)

    def test_late_result_is_void(self):
        lane = self.hung()
        self.release.set()
        lane.thread.join(10)
        for safe in (4, 5):
            self.assertEqual(lane.poll(safe=safe), "fallback")
        self.assertEqual(self.candidate(), FOOTSTEPS)
        receipt = json.loads(
            (self.rundir / "haunt-evidence" / "receipt.json").read_text()
        )
        self.assertEqual(
            (receipt["outcome"], receipt["late_outcome"]), ("deadline", "ready")
        )
        with self.assertRaises(ValueError):
            hound_author.read_evidence(self.rundir / "haunt-evidence")
        self.assertEqual(self.sends(), 1)


class RestoreTests(HoundBase):
    """A restored game follows the record and never asks again."""

    def restored(self, backend="default"):
        return lane_mod.HoundLane(
            self.rundir,
            self.backend(create=self.no_send) if backend == "default" else backend,
            validator=FakePrecheck(),
        )

    @staticmethod
    def no_send(**kwargs):
        raise AssertionError("a restored lane sent a request")

    def test_idle(self):
        lane = self.restored()
        self.assertEqual(lane.state, "idle")
        self.assertIsNone(self.candidate())

    def test_requested_without_evidence_falls_back(self):
        record = lane_mod.read_lane(self.rundir)
        shared.write_record(self.rundir, lane_mod.LANE, record, "requested", 1)
        self.backtracked()
        lane = self.restored()
        self.assertEqual(lane.state, "failed")
        self.assertEqual(lane.poll(safe=2), "fallback")
        self.assertEqual(self.record()["outcome"], "abandoned_on_restore")
        self.assertEqual((self.candidate(), self.sends()), (FOOTSTEPS, 0))

    def test_requested_with_a_ready_answer_publishes_it(self):
        self.backtracked()
        lane = self.lane()
        self.assertEqual(lane.poll(safe=1), "requested")
        lane.wait(10)
        # The director died before it settled the request.
        self.assertEqual(self.record()["step"], "requested")
        restored = self.restored()
        self.assertEqual(restored.state, "ready")
        self.assertEqual(restored.poll(safe=2), "published")
        self.assertEqual(self.candidate(), SOURCE.encode())
        self.assertEqual(self.sends(), 1)

    def test_ready_published_fallback_and_no_model_are_kept(self):
        self.backtracked()
        self.assertEqual(self.drive(self.lane()), "published")
        for _ in range(2):
            lane = self.restored()
            self.assertEqual(lane.poll(safe=3), "published")
        self.assertEqual((self.candidate(), self.sends()), (SOURCE.encode(), 1))

    def test_fallback_is_kept(self):
        self.backtracked()
        self.assertEqual(self.drive(self.lane(self.backend("not json"))), "fallback")
        lane = self.restored()
        self.assertEqual(lane.poll(safe=3), "fallback")
        self.assertEqual((self.candidate(), self.sends()), (FOOTSTEPS, 2))

    def test_no_model_is_kept_and_publish_is_idempotent(self):
        lane_mod.HoundLane(self.rundir, None, validator=None)
        lane = self.restored(backend=None)
        self.assertEqual(lane.state, "no_model")
        self.assertEqual((self.candidate(), self.sends()), (FOOTSTEPS, 0))

    def test_restore_without_a_backend_falls_back_never_asks(self):
        record = lane_mod.read_lane(self.rundir)
        shared.write_record(self.rundir, lane_mod.LANE, record, "requested", 1)
        lane = self.restored(backend=None)
        self.assertEqual(lane.poll(safe=2), "fallback")
        self.assertEqual((self.candidate(), self.sends()), (FOOTSTEPS, 0))

    def test_conflicting_candidate_fails_closed(self):
        (self.rundir / "haunting.lua").write_bytes(b"return function(c) end")
        os.chmod(self.rundir / "haunting.lua", 0o600)
        self.backtracked()
        lane = self.lane()
        lane.poll(safe=1)
        lane.wait(10)
        with self.assertRaises(ValueError):
            lane.poll(safe=1)

    def test_tampered_lane_fails_closed(self):
        good = json.loads((self.rundir / lane_mod.LANE).read_text())
        for bad in (
            dict(good, step="admitted"),
            dict(good, evidence="curio-evidence"),
            dict(good, error_type="LaneDeadline"),
            dict(good, extra=1),
        ):
            with self.subTest(bad=bad):
                (self.rundir / lane_mod.LANE).write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    lane_mod.read_lane(self.rundir)


class ReplayRecordTests(HoundBase):
    """The engine's window, bound after the game and staged before replay."""

    def finished(self, detail="pre_admitted"):
        self.backtracked()
        self.assertEqual(self.drive(self.lane()), "published")
        row = json.loads(self.backtrack)
        events = [
            dict(
                row,
                seq=row["seq"] + 1,
                turn=row["turn"] + 3,
                event="haunting",
                detail="budget",
            ),
            dict(
                row,
                seq=row["seq"] + 2,
                turn=row["turn"] + 9,
                event="haunting",
                detail=detail,
            ),
        ]
        self.events(
            self.before
            + [self.backtrack]
            + [json.dumps(e, separators=(",", ":")).encode() + b"\n" for e in events]
        )
        return events[0]

    def test_record_and_stage(self):
        first = self.finished()
        admission = lane_mod.record_admission(self.rundir)
        self.assertEqual(
            (admission["turn"], admission["seq"], admission["detail"]),
            (first["turn"], first["seq"], "budget"),
        )
        self.assertEqual(admission["evidence"], "haunt-evidence")
        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        staged = lane_mod.stage_replay(replay, self.rundir)
        self.assertEqual(staged, admission)
        self.assertEqual((replay / "haunting.lua").read_bytes(), SOURCE.encode())
        self.assertEqual(
            (replay / "haunting-due").read_bytes(),
            b"%d %d\n" % (first["turn"], first["seq"]),
        )
        # verify_replay: the same window and bytes pass, any other fails.
        (replay / "events.jsonl").write_bytes(
            (self.rundir / "events.jsonl").read_bytes()
        )
        self.assertEqual(
            lane_mod.verify_replay(replay, self.rundir)["seq"], first["seq"]
        )
        later = self.root / "later"
        later.mkdir(mode=0o700)
        lane_mod.stage_replay(later, self.rundir)
        rows = [json.loads(x) for x in lines(self.rundir / "events.jsonl")]
        for e in rows:
            if e["event"] == "haunting":
                e["seq"] += 1
        (later / "events.jsonl").write_text(
            "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in rows)
        )
        with self.assertRaises(ValueError):
            lane_mod.verify_replay(later, self.rundir)

    def test_fallback_runs_record_footsteps(self):
        self.backtracked()
        self.assertEqual(self.drive(self.lane(self.backend("not json"))), "fallback")
        row = json.loads(self.backtrack)
        e = dict(row, seq=row["seq"] + 1, event="haunting", detail="pre_admitted")
        self.events(
            self.before
            + [self.backtrack, json.dumps(e, separators=(",", ":")).encode() + b"\n"]
        )
        admission = lane_mod.record_admission(self.rundir)
        self.assertEqual(admission["evidence"], None)
        self.assertEqual(admission["source_sha256"], hound_author._sha(FOOTSTEPS))

    def test_tampered_source_is_caught(self):
        self.finished()
        lane_mod.record_admission(self.rundir)
        source = self.rundir / "haunt-evidence" / "source.lua"
        os.chmod(source, 0o600)
        source.write_bytes(b"return function(c) return {dx=1,dy=0,state=0} end")
        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            lane_mod.stage_replay(replay, self.rundir)
        self.assertFalse((replay / "haunting.lua").exists())

    def test_tampered_fallback_source_is_caught(self):
        # A fallback run has no evidence chain: the admission's hash is the
        # only binding between the recorded candidate and what is staged.
        self.test_fallback_runs_record_footsteps()
        candidate = self.rundir / "haunting.lua"
        os.replace(candidate, self.rundir / "old.lua")
        candidate.write_bytes(b"return function(c) return {dx=1,dy=0,state=0} end")
        os.chmod(candidate, 0o600)
        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            lane_mod.stage_replay(replay, self.rundir)
        self.assertFalse((replay / "haunting.lua").exists())

    def test_staging_never_builds_a_transport(self):
        self.finished()
        lane_mod.record_admission(self.rundir)
        from unittest.mock import patch

        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        with (
            patch.object(hound_author, "author_hound", side_effect=AssertionError),
            patch.object(hound_author, "build_backend", side_effect=AssertionError),
            patch.object(xai, "build", side_effect=AssertionError),
        ):
            lane_mod.stage_replay(replay, self.rundir)


class HoundValidatorTests(unittest.TestCase):
    """The host pre-check through the engine's own chaos_lua_step."""

    LIBRARY = Path(__file__).resolve().parents[2] / "dnethackdir/curio-validator.so"

    def setUp(self):
        if not self.LIBRARY.is_file():
            self.skipTest("needs the CHAOS=1 make install validator library")
        self.v = hound_author.HoundValidator(self.LIBRARY)

    def test_footsteps_passes(self):
        r = self.v.validate(FOOTSTEPS)
        self.assertEqual((r["admitted"], r["grid_failures"]), (True, 0), r)
        self.assertEqual(r["grid_calls"], len(hound_author.GRID))

    def test_obviously_failing_programs_are_caught(self):
        for name, source, failure in (
            (
                "idle",
                b"return function(c) return {dx=0,dy=0,state=0} end",
                "never_moves",
            ),
            (
                "range",
                b"return function(c) return {dx=2,dy=0,state=0} end",
                "native_step",
            ),
            ("loop", b"return function(c) while true do end end", "native_step"),
            (
                "library",
                b"return function(c) return {dx=math.floor(1),dy=0,state=0} end",
                "native_step",
            ),
            ("shape", b"return function(c) return {dx=1,dy=0} end", "native_step"),
            ("syntax", b"return function(c", "native_step"),
        ):
            with self.subTest(name):
                r = self.v.validate(source)
                self.assertEqual((r["admitted"], r["failure"]), (False, failure), r)


if __name__ == "__main__":
    unittest.main()
