"""Slice 3a offline: the director's curio lane. Fake transports and a fake
validator only; no provider, no Hermes, no native library, no game.

What the player sees is decided by one thing the lane controls: whether
curio.lua is ever published into the run directory (the engine admits only a
published source, and shows only its own admission line). Each failure row of
proposal 3.8 therefore asserts that nothing is published and that the lane's
durable record says why.
"""

import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

from chaos import curio_author, curio_director as lane_mod, xai
from chaos.author_config import resolve
from chaos.history import snapshot_history

from test_curio_grounding import (
    HISTORY,
    MODEL,
    SOURCE,
    FakeClient,
    FakeValidator,
    envelope,
)


def event_line(**fields):
    return json.dumps(fields, separators=(",", ":")).encode() + b"\n"


class LaneBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        os.chmod(self.root, 0o700)
        self.ledger = xai.XaiLedger(self.root / "ledger" / "xai-ledger.jsonl")
        self.config = resolve("xai-oauth", MODEL)
        self.rundir = self.root / ("run-" + uuid.uuid4().hex[:8])
        self.rundir.mkdir(mode=0o700)
        # A living game: the capture up to (not including) its final quit.
        lines = HISTORY.read_bytes().splitlines(keepends=True)
        assert json.loads(lines[-1])["event"] == "death"
        (self.rundir / "events.jsonl").write_bytes(b"".join(lines[:-1]))
        os.chmod(self.rundir / "events.jsonl", 0o600)
        self.record = lane_mod.new_lane(self.rundir, seed=7)

    def backend(self, content=None, create=None):
        client = FakeClient(envelope() if content is None else content)
        if create is not None:
            client.chat.completions.create = create
        self.client = client
        return curio_author.build_backend(
            self.config,
            ledger=self.ledger,
            run_id="placeholder",
            client_factory=lambda: (client, MODEL),
        )

    def lane(self, backend=None, validator=None, **kwargs):
        lane = lane_mod.CurioLane(
            self.rundir,
            self.backend() if backend is None else backend,
            validator=FakeValidator() if validator is None else validator,
            **kwargs,
        )
        # The fixture game later reached DL3 (native "expired"); these tests
        # replay the decision as of an earlier point where the curio was
        # VIRGIN. note() still moves it on, as in the director loop.
        lane._phase = "VIRGIN"
        return lane

    def drive(self, lane, *, planned_cost=0, timeout=10):
        state = lane.poll(planned_cost=planned_cost, safe=5)
        end = time.monotonic() + timeout
        while state == "requested" and time.monotonic() < end:
            lane.wait(0.05)
            state = lane.poll(planned_cost=planned_cost, safe=5)
        return state

    def published(self):
        return (self.rundir / "curio.lua").exists()

    def sends(self):
        return sum(r["status"] == "reserved" for r in self.ledger.rows())


class TriggerTests(LaneBase):
    def history(self):
        return snapshot_history(self.rundir)[0]

    def test_phase_comes_from_the_engines_events(self):
        self.assertEqual(lane_mod.curio_phase(self.rundir), "EXPIRED")
        lane = lane_mod.CurioLane(
            self.rundir, self.backend(), validator=FakeValidator()
        )
        self.assertEqual(lane.phase(), "EXPIRED")
        self.assertEqual(lane.poll(safe=5), "idle")
        self.assertFalse(lane.active)
        self.assertEqual(self.sends(), 0)

    def test_fixture_history_qualifies(self):
        h = self.history()
        self.assertGreaterEqual(h.latest["turn"], lane_mod.TRIGGER_TURNS)
        self.assertTrue(lane_mod.trigger_ready(h))

    def test_turns_episodes_whispers_and_budget(self):
        h = self.history()
        cases = [
            (dict(turn=149), {}, False),
            (dict(turn=150), {}, True),
            (dict(budget=0), {}, False),
            # The planned whisper needs the last unit: no curio request.
            (dict(budget=1), dict(planned_cost=1), False),
            (dict(budget=2), dict(planned_cost=1), True),
        ]
        for latest, kwargs, expected in cases:
            with self.subTest(latest=latest, kwargs=kwargs):
                base = h.latest
                h.latest = dict(base, **latest)
                try:
                    self.assertIs(lane_mod.trigger_ready(h, **kwargs), expected)
                finally:
                    h.latest = base
        h = self.history()
        h.prior_whispers, h.prior_coverage = [], dict(shown=0, omitted=0)
        self.assertTrue(lane_mod.trigger_ready(h))  # 3 whistling episodes
        h.episodes = dict(h.episodes, episodes=[dict(count=1)])
        self.assertFalse(lane_mod.trigger_ready(h))
        h.prior_coverage = dict(shown=0, omitted=1)
        self.assertTrue(lane_mod.trigger_ready(h))  # one seen whisper suffices

    def test_one_request_per_game_and_phase_must_be_virgin(self):
        lane = self.lane()
        lane.note(dict(event="curio", detail="expired"))
        self.assertEqual(lane.poll(safe=5), "idle")
        self.assertFalse(lane.active)
        self.assertEqual(self.sends(), 0)
        lane = self.lane()
        lane._phase = "VIRGIN"
        self.assertEqual(self.drive(lane), "published")
        for _ in range(3):
            lane.poll(safe=6)
        self.assertEqual(self.sends(), 1)
        self.assertEqual(self.lane().poll(safe=7), "published")
        self.assertEqual(self.sends(), 1)

    def test_planned_whisper_keeps_the_last_unit(self):
        lane = self.lane()
        latest = dict(snapshot_history(self.rundir)[0].latest)
        self.assertEqual(latest["budget"], 2)
        self.assertEqual(lane.poll(planned_cost=2, safe=5, latest=latest), "idle")
        self.assertEqual(self.sends(), 0)

    def test_poll_never_blocks_on_the_transport(self):
        release = threading.Event()
        client = FakeClient(envelope())
        original = client.create

        def slow(**kwargs):
            release.wait(10)
            return original(**kwargs)

        lane = self.lane(self.backend(create=slow))
        started = time.monotonic()
        self.assertEqual(lane.poll(safe=5), "requested")
        self.assertEqual(lane.poll(safe=5), "requested")
        self.assertLess(time.monotonic() - started, 1.0)
        release.set()
        self.assertEqual(self.drive(lane), "published")

    def test_lane_off_without_configuration(self):
        (self.rundir / "curio-lane.json").unlink()
        lane = lane_mod.CurioLane(self.rundir, None, validator=None)
        self.assertEqual(lane.state, "off")
        self.assertFalse(lane.active)
        self.assertEqual(lane.poll(safe=5), "off")


class PublishTests(LaneBase):
    def test_ready_curio_is_published_by_rename_with_one_link(self):
        lane = self.lane()
        self.assertEqual(self.drive(lane), "published")
        target = self.rundir / "curio.lua"
        self.assertEqual(target.read_text(), SOURCE)
        self.assertEqual(target.stat().st_nlink, 1)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertFalse(
            any(p.name.startswith(".publish-") for p in self.rundir.iterdir())
        )
        install = json.loads(
            (self.rundir / "curio-evidence" / "install.json").read_text()
        )
        self.assertEqual(install["v"], 2)
        self.assertEqual(install["advisory_safe"], 5)
        lane_record = lane_mod.read_lane(self.rundir)
        self.assertEqual(
            (lane_record["step"], lane_record["evidence"]),
            ("published", "curio-evidence"),
        )

    def test_ledger_run_id_is_the_recorded_game(self):
        backend = self.backend()
        self.lane(backend)
        self.assertEqual(backend.run_id, self.record["game"])

    def test_publish_never_replaces_a_different_source(self):
        (self.rundir / "curio.lua").write_text("return {}")
        lane = self.lane()
        with self.assertRaises(ValueError):
            self.drive(lane)

    def test_layer_follows_the_recorded_seed(self):
        self.drive(self.lane())
        prompt = json.loads(
            (self.rundir / "curio-evidence" / "prompt.json").read_text()
        )
        self.assertEqual(prompt["game_seed"], 7)


class FailureTableTests(LaneBase):
    """Proposal 3.8, one row each. The player sees nothing in every row below:
    nothing is published, so the engine has nothing to admit or show."""

    def assert_nothing(self, lane, outcome, sends):
        self.assertEqual(self.drive(lane), "failed")
        self.assertFalse(self.published())
        record = lane_mod.read_lane(self.rundir)
        self.assertEqual(record["outcome"], outcome)
        self.assertEqual(self.sends(), sends)

    def failing(self, status, header="0", error=None):
        class Failure(RuntimeError):
            status_code = status
            response = type("R", (), {"headers": {"Retry-After": header}})()

        def create(**kwargs):
            raise error or Failure("fixture")

        return self.backend(create=create)

    def test_provider_error(self):
        self.assert_nothing(self.lane(self.failing(None)), "transport_failed", 3)

    def test_502(self):
        self.assert_nothing(self.lane(self.failing(502)), "transport_failed", 3)

    def test_429_honours_retry_after(self):
        with patch("chaos.curio_author.time.sleep") as sleep:
            self.assert_nothing(
                self.lane(self.failing(429, "3")), "transport_failed", 3
            )
        self.assertEqual([c.args for c in sleep.call_args_list], [(3.0,), (3.0,)])

    def test_deadline(self):
        self.assert_nothing(
            self.lane(self.failing(None, error=TimeoutError())), "deadline", 1
        )

    def test_non_json_regenerates_once(self):
        self.assert_nothing(self.lane(self.backend("not json")), "envelope_rejected", 2)
        self.assertTrue((self.rundir / "curio-evidence-2" / "receipt.json").exists())

    def test_oversize_regenerates_once(self):
        big = envelope(note="x" * 9000)
        self.assert_nothing(self.lane(self.backend(big)), "envelope_rejected", 2)

    def test_regeneration_can_succeed(self):
        replies = iter(["not json", envelope()])
        client = FakeClient(envelope())
        original = client.create

        def create(**kwargs):
            client.content = next(replies)
            return original(**kwargs)

        lane = self.lane(self.backend(create=create))
        self.assertEqual(self.drive(lane), "published")
        self.assertEqual(
            lane_mod.read_lane(self.rundir)["evidence"], "curio-evidence-2"
        )
        self.assertEqual(self.sends(), 2)

    def test_invalid_lua(self):
        self.assert_nothing(
            self.lane(validator=FakeValidator(admitted=False)), "native_rejected", 1
        )

    def test_grid_failure(self):
        validator = FakeValidator()
        validate = validator.validate

        def grid(*args):
            result = validate(*args)
            return dict(result, admitted=False, failure="grid", grid_failures=1)

        validator.validate = grid
        self.assert_nothing(self.lane(validator=validator), "native_rejected", 1)

    def test_truth_reject(self):
        self.assert_nothing(
            self.lane(validator=FakeValidator(texts=("It gives you a key.",))),
            "truth_rejected",
            1,
        )

    def test_dl3_first(self):
        release = threading.Event()
        client = FakeClient(envelope())
        original = client.create

        def slow(**kwargs):
            release.wait(10)
            return original(**kwargs)

        lane = self.lane(self.backend(create=slow))
        self.assertEqual(lane.poll(safe=5), "requested")
        # Native expiry on reaching DL3, observed while authoring runs.
        lane.note(dict(event="curio", detail="expired"))
        release.set()
        self.assertEqual(self.drive(lane), "failed")
        self.assertFalse(self.published())
        self.assertEqual(
            lane_mod.read_lane(self.rundir)["outcome"], "closed_before_publish"
        )

    def test_no_placement_square_is_the_engines_row(self):
        # Admitted, then native placement_unavailable: the lane's part ends at
        # publication; the engine shows its admission line and has already
        # charged (today's rule). Asserted natively in test_curio_admission /
        # the Tier A director evidence; here: published once, never retracted.
        lane = self.lane()
        self.assertEqual(self.drive(lane), "published")
        for detail in ("pre_admitted", "admitted", "placement_unavailable"):
            lane.note(dict(event="curio", detail=detail))
        self.assertEqual(lane.poll(safe=9), "published")
        self.assertTrue(self.published())
        self.assertEqual(self.sends(), 1)

    def test_provider_unreachable_at_startup(self):
        lane = lane_mod.CurioLane(self.rundir, None, validator=FakeValidator())
        self.assertEqual(lane.state, "no_model")
        self.assertEqual(lane_mod.read_lane(self.rundir)["outcome"], "no_backend")
        self.assertEqual(lane.poll(safe=5), "no_model")
        self.assertFalse(lane.active)
        # Restore follows the recorded state; it never retries the provider.
        restored = lane_mod.CurioLane(
            self.rundir, self.backend(), validator=FakeValidator()
        )
        self.assertEqual(restored.poll(safe=6), "no_model")
        self.assertFalse(self.published())
        self.assertEqual(self.sends(), 0)


class RestoreTests(LaneBase):
    def test_in_flight_generation_is_abandoned_never_resent(self):
        lane_mod._write_lane(self.rundir, self.record, "requested", 4)
        lane = self.lane()
        self.assertEqual(lane.state, "failed")
        self.assertEqual(
            lane_mod.read_lane(self.rundir)["outcome"], "abandoned_on_restore"
        )
        for _ in range(3):
            lane.poll(safe=6)
        self.assertEqual(self.sends(), 0)
        self.assertFalse(self.published())

    def test_ready_but_unpublished_is_published_without_a_request(self):
        first = self.lane()
        first.poll(safe=5)
        first.wait(10)  # authored; the director died before _finished
        self.assertEqual(lane_mod.read_lane(self.rundir)["step"], "requested")
        sends = self.sends()
        restored = self.lane()
        self.assertEqual(restored.state, "ready")
        self.assertEqual(restored.poll(safe=8), "published")
        self.assertEqual(self.sends(), sends)
        self.assertEqual((self.rundir / "curio.lua").read_text(), SOURCE)

    def test_recorded_ready_publishes_and_published_stays_published(self):
        lane = self.lane()
        lane.poll(safe=5)
        lane.wait(10)
        lane_mod._write_lane(
            self.rundir, self.record, "ready", 5, "ready", "curio-evidence"
        )
        self.assertEqual(self.lane().poll(safe=6), "published")
        sends = self.sends()
        self.assertEqual(self.lane().poll(safe=7), "published")
        self.assertEqual(self.sends(), sends)

    def test_crash_between_publish_and_record_is_idempotent(self):
        lane = self.lane()
        lane.poll(safe=5)
        lane.wait(10)
        lane_mod._write_lane(
            self.rundir, self.record, "ready", 5, "ready", "curio-evidence"
        )
        lane_mod.publish_source(self.rundir, SOURCE.encode())
        self.assertEqual(self.lane().poll(safe=6), "published")

    def test_tampered_lane_fails_closed(self):
        good = json.loads((self.rundir / "curio-lane.json").read_text())
        for bad in (
            dict(good, step="maybe"),
            dict(good, evidence="../x"),
            dict(good, seed=-1),
            dict(good, game="NOT HEX"),
            {k: v for k, v in good.items() if k != "game"},
        ):
            with self.subTest(bad=bad):
                (self.rundir / "curio-lane.json").write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    lane_mod.read_lane(self.rundir)


class ReplayStagingTests(LaneBase):
    def recorded(self):
        self.drive(self.lane())
        evidence = self.rundir / "curio-evidence"
        with open(self.rundir / "events.jsonl", "ab") as f:
            f.write(
                event_line(event="curio", phase="result", detail="pre_admitted", safe=6)
            )
        used = self.rundir / "curio-used.lua"
        used.write_text(SOURCE)
        used.chmod(0o600)
        return evidence

    def test_record_stage_verify(self):
        evidence = self.recorded()
        admission = lane_mod.record_admission(self.rundir, evidence)
        self.assertEqual(admission["safe"], 6)
        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        self.assertEqual(lane_mod.stage_replay(replay, evidence), admission)
        self.assertEqual((replay / "curio-safe").read_bytes(), b"6\n")
        self.assertEqual((replay / "curio.lua").read_text(), SOURCE)
        for name in ("curio-safe", "curio.lua"):
            self.assertEqual((replay / name).stat().st_nlink, 1)
        shutil.copyfile(self.rundir / "events.jsonl", replay / "events.jsonl")
        shutil.copyfile(self.rundir / "curio-used.lua", replay / "curio-used.lua")
        os.chmod(replay / "curio-used.lua", 0o600)
        self.assertEqual(lane_mod.verify_replay(replay, evidence), admission)

    def test_replay_at_a_different_index_is_caught(self):
        evidence = self.recorded()
        lane_mod.record_admission(self.rundir, evidence)
        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        lane_mod.stage_replay(replay, evidence)
        (replay / "events.jsonl").write_bytes(
            event_line(event="curio", phase="result", detail="pre_admitted", safe=7)
        )
        shutil.copyfile(self.rundir / "curio-used.lua", replay / "curio-used.lua")
        os.chmod(replay / "curio-used.lua", 0o600)
        with self.assertRaises(ValueError):
            lane_mod.verify_replay(replay, evidence)

    def test_admission_must_match_the_evidence(self):
        evidence = self.recorded()
        (self.rundir / "curio-used.lua").write_text("return {}")
        with self.assertRaises(ValueError):
            lane_mod.record_admission(self.rundir, evidence)

    def test_staging_never_builds_a_transport(self):
        evidence = self.recorded()
        lane_mod.record_admission(self.rundir, evidence)
        replay = self.root / "replay"
        replay.mkdir(mode=0o700)
        with (
            patch.object(xai.XaiBackend, "generate", side_effect=AssertionError),
            patch.object(curio_author, "author_curio", side_effect=AssertionError),
            patch.object(curio_author, "build_backend", side_effect=AssertionError),
        ):
            lane_mod.stage_replay(replay, evidence)


if __name__ == "__main__":
    unittest.main()
