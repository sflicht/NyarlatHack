"""Deterministic live poll boundaries; real mailbox/reader, no game or model."""

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from chaos import director, launcher
from test_director import REQ, ack, append, event


# Exact first five records from the reproduced native launcher failure:
# /tmp/nyarl-launcher-gameplay-2t1ezjsl/pack-restore/run/events.jsonl.
# Captured evidence, not a synthetic claim of engine execution in these tests.
NATIVE = [
    json.loads(line)
    for line in """
{"v":1,"seq":1,"turn":1,"safe":0,"event":"session","phase":"result","detail":"new","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":13,"hp_max":13,"power":10,"power_max":10}}
{"v":1,"seq":2,"turn":1,"safe":0,"event":"level_enter","phase":"result","detail":"","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":13,"hp_max":13,"power":10,"power_max":10}}
{"v":1,"seq":3,"turn":1,"safe":1,"event":"safe_point","phase":"result","detail":"level_enter","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":0,"vitals":{"hp":13,"hp_max":13,"power":10,"power_max":10}}
{"v":1,"seq":4,"turn":1,"safe":1,"event":"telegraph","phase":"result","detail":"ambient","sanity":100,"insight":0,"budget":2,"spent":0,"reserved":0,"last_id":1,"vitals":{"hp":13,"hp_max":13,"power":10,"power_max":10}}
{"v":1,"seq":5,"turn":1,"safe":1,"event":"ack","phase":"result","detail":"ok","sanity":100,"insight":0,"budget":1,"spent":1,"reserved":0,"last_id":1,"vitals":{"hp":13,"hp_max":13,"power":10,"power_max":10},"id":1,"status":"accepted","mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1,"cost":1,"expires":0}
""".strip().splitlines()
]


class LiveAckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.serial = 0

    def setup_run(self, initial=None, existing=None):
        self.serial += 1
        self.path = self.root / str(self.serial)
        self.path.mkdir(mode=0o700)
        self.events = self.path / "events.jsonl"
        self.target = self.path / "whisper.json"
        self.state = director.State()
        append(self.events, *(initial if initial is not None else [event(safe=0)]))
        if existing is not None:
            self.write_mailbox(existing)
        self.now = 0.0
        self.sleeps = 0

    def write_mailbox(self, request):
        self.target.write_bytes(director.encode_request(request))
        self.target.chmod(0o600)

    def run_loop(self, loop, step, backend=None, *, preflight=None):
        backend = backend or director.ScheduleBackend([REQ, dict(REQ, id=2, at=2)])

        def sleep(seconds):
            self.assertGreater(seconds, 0)
            self.now += seconds
            self.sleeps += 1
            step(self.sleeps)

        with (
            patch.object(director.time, "monotonic", side_effect=lambda: self.now),
            patch.object(director.time, "sleep", side_effect=sleep),
        ):
            if loop == "director":
                with patch.object(director, "State", return_value=self.state):
                    return director.run(self.path, backend, max_runtime=1, poll=0.125)
            read_fd, write_fd = os.pipe()
            try:
                with director.Mailbox(self.path) as box:
                    reader = director.EventReader(self.events)
                    if preflight is not None:
                        launcher._observe(reader, self.state, box, backend)
                        preflight()
                    launcher._offline_loop(
                        box,
                        backend,
                        reader,
                        self.state,
                        SimpleNamespace(max_runtime=1, poll=0.125, max_submissions=12),
                        write_fd,
                    )
                self.assertEqual(os.read(read_fd, 1), b"R")
            finally:
                os.close(read_fd)
                try:
                    os.close(write_fd)
                except OSError:
                    pass  # Success closes the readiness writer inside the loop.

    def assert_pending(self, raw):
        self.assertEqual(self.target.read_bytes(), raw)
        self.assertEqual(self.state.accepted, {})
        self.assertEqual(self.state.acks, {})
        self.assertEqual(self.state.active, {})

    def test_split_native_telegraph_partial_ack_then_next_proposal(self):
        for loop in ("director", "launcher"):
            for existing in (None, REQ):
                for kind in ("schedule", "random"):
                    with self.subTest(loop=loop, existing=existing, backend=kind):
                        self.setup_run(NATIVE[:2], existing)
                        # Seed 2 chooses the captured ambient value 1 at safe 0.
                        backend = (
                            None if kind == "schedule" else director.RandomBackend(2)
                        )
                        raw = []
                        ack_raw = json.dumps(NATIVE[4]).encode() + b"\n"

                        def step(n):
                            if n == 1:
                                raw.append(self.target.read_bytes())
                                self.assertEqual(json.loads(raw[0]), REQ)
                                self.assert_pending(raw[0])
                                append(self.events, NATIVE[2])
                            elif n == 2:
                                self.assert_pending(raw[0])
                                append(self.events, NATIVE[3])
                            elif n == 3:
                                self.assert_pending(raw[0])
                                with self.events.open("ab") as f:
                                    f.write(ack_raw[:40])
                            elif n == 4:
                                self.assert_pending(raw[0])
                                with self.events.open("ab") as f:
                                    f.write(ack_raw[40:])
                            else:
                                self.assertEqual(self.state.accepted, {1: REQ})
                                proposal = json.loads(self.target.read_bytes())
                                self.assertEqual(
                                    (proposal["id"], proposal["at"]), (2, 2)
                                )

                        result = self.run_loop(loop, step, backend)
                        self.assertEqual(self.sleeps, 8)
                        if result:
                            self.assertEqual(result["reason"], "runtime_cap")
                            self.assertEqual(
                                result["submitted"], 2 if existing is None else 1
                            )

    def test_missing_live_ack_stops_at_runtime_cap_without_acceptance(self):
        for loop in ("director", "launcher"):
            with self.subTest(loop=loop):
                self.setup_run()
                raw = []

                def step(n):
                    if n == 1:
                        raw.append(self.target.read_bytes())
                        append(
                            self.events,
                            event(2, event="telegraph", detail="ambient", last_id=1),
                        )
                    self.assert_pending(raw[0])

                result = self.run_loop(loop, step)
                self.assertEqual(self.now, 1)
                self.assertEqual(self.sleeps, 8)
                if result:
                    self.assertEqual(result["reason"], "runtime_cap")
                    self.assertEqual(result["submitted"], 1)

    def test_live_conflicts_fail_without_overwriting_or_retiming(self):
        for loop in ("director", "launcher"):
            for failure in (
                "changed_payload",
                "changed_with_ack",
                "changed_future_payload",
                "missing_mailbox",
                "wrong_ack",
                "wrong_ack_unconsumed",
                "expired_safe",
                "expired_unconsumed",
                "early_safe",
                "advanced_id",
                "wrong_telegraph",
                "wrong_phase",
                "no_telegraph",
            ):
                with self.subTest(loop=loop, failure=failure):
                    self.setup_run()
                    preserved = []

                    def step(n):
                        self.assertEqual(
                            n, 1, "invalid evidence must fail on the next poll"
                        )
                        e = event(2, event="telegraph", detail="ambient", last_id=1)
                        if failure in (
                            "changed_payload",
                            "changed_with_ack",
                            "changed_future_payload",
                        ):
                            self.write_mailbox(dict(REQ, value=2))
                        if failure == "changed_future_payload":
                            e.update(last_id=0, safe=0, event="safe_point")
                        if failure == "missing_mailbox":
                            self.target.unlink()
                        if failure == "expired_safe":
                            e["safe"] = 2
                        if failure == "expired_unconsumed":
                            e.update(safe=2, last_id=0, event="safe_point")
                        if failure == "early_safe":
                            e["safe"] = 0
                        if failure == "wrong_ack_unconsumed":
                            e.update(safe=0, last_id=0)
                        if failure == "advanced_id":
                            e["last_id"] = 2
                        if failure == "wrong_telegraph":
                            e["detail"] = "ward_efficacy"
                        if failure == "wrong_phase":
                            e["phase"] = "attempt"
                        if failure == "no_telegraph":
                            e["event"] = "safe_point"
                        append(self.events, e)
                        if failure in ("wrong_ack", "changed_with_ack"):
                            append(self.events, ack(3, dict(REQ, value=2)))
                        if failure == "wrong_ack_unconsumed":
                            append(
                                self.events,
                                ack(3, dict(REQ, value=2), safe=0, last_id=0),
                            )
                        preserved.append(
                            self.target.read_bytes() if self.target.exists() else None
                        )

                    with self.assertRaises(ValueError):
                        self.run_loop(loop, step)
                    self.assertEqual(self.sleeps, 1)
                    self.assertEqual(
                        self.target.read_bytes() if self.target.exists() else None,
                        preserved[0],
                    )

    def test_advanced_safe_after_live_wait_is_not_still_inflight(self):
        for loop in ("director", "launcher"):
            with self.subTest(loop=loop):
                self.setup_run()

                def step(n):
                    if n == 1:
                        append(
                            self.events,
                            event(2, event="telegraph", detail="ambient", last_id=1),
                        )
                    elif n == 2:
                        self.assertEqual(self.state.accepted, {})
                        append(self.events, event(3, safe=2, last_id=1))
                    else:
                        self.fail("advanced safe index must not keep waiting")

                with self.assertRaises(ValueError):
                    self.run_loop(loop, step)
                self.assertEqual(self.sleeps, 2)

    def test_initial_consumed_missing_ack_is_strict_in_all_entrypoints(self):
        for entry in ("director", "launcher", "observe"):
            with self.subTest(entry=entry):
                self.setup_run(NATIVE[:4], REQ)
                raw = self.target.read_bytes()
                with self.assertRaisesRegex(
                    ValueError, "consumed mailbox lacks exact ACK"
                ):
                    if entry == "observe":
                        with director.Mailbox(self.path) as box:
                            launcher._observe(
                                director.EventReader(self.events),
                                self.state,
                                box,
                                director.ScheduleBackend([REQ]),
                            )
                    else:
                        self.run_loop(
                            entry, lambda _: self.fail("startup must not wait")
                        )
                self.assertEqual(self.target.read_bytes(), raw)

    def test_launcher_readiness_rechecks_consumed_after_observe(self):
        self.setup_run(NATIVE[:2], REQ)
        with self.assertRaisesRegex(ValueError, "consumed mailbox lacks exact ACK"):
            self.run_loop(
                "launcher",
                lambda _: self.fail("readiness must not wait"),
                preflight=lambda: append(self.events, *NATIVE[2:4]),
            )

    def test_initial_overdue_pending_is_not_adopted_as_live(self):
        for entry in ("director", "launcher", "observe"):
            for safe in (1, 2):
                with self.subTest(entry=entry, safe=safe):
                    self.setup_run([event(safe=safe)], REQ)
                    with self.assertRaisesRegex(ValueError, "missed its safe index"):
                        if entry == "observe":
                            with director.Mailbox(self.path) as box:
                                launcher._observe(
                                    director.EventReader(self.events),
                                    self.state,
                                    box,
                                    director.ScheduleBackend([REQ]),
                                )
                        else:
                            self.run_loop(
                                entry, lambda _: self.fail("startup must not wait")
                            )

    def test_rejected_ack_after_live_wait_is_not_schedule_acceptance(self):
        for loop in ("director", "launcher"):
            with self.subTest(loop=loop):
                self.setup_run()

                def step(n):
                    if n == 1:
                        append(
                            self.events,
                            event(2, event="telegraph", detail="ambient", last_id=1),
                        )
                    elif n == 2:
                        append(
                            self.events,
                            ack(
                                3,
                                status="rejected",
                                detail="log_failure",
                                spent=0,
                                budget=2,
                            ),
                        )
                    else:
                        self.fail("rejected schedule must not retry")

                with self.assertRaisesRegex(ValueError, "schedule missed or rejected"):
                    self.run_loop(loop, step)
                self.assertEqual(self.sleeps, 2)
                self.assertEqual(self.state.accepted, {})
                self.assertEqual(self.state.acks[1]["status"], "rejected")
                self.assertEqual(json.loads(self.target.read_bytes()), REQ)


if __name__ == "__main__":
    unittest.main()
