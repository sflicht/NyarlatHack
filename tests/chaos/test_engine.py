"""Real transport/admission tests; UI callback records ordering, not effects."""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from test_protocol import ROOT, REQUEST


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="chaos-io-bin-")
        cls.exe = pathlib.Path(cls.tmp.name) / "io"
        if (ROOT / "src/chaos_io.c").exists():
            subprocess.run(
                [
                    "cc",
                    "-std=c99",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-pedantic",
                    "-I" + str(ROOT / "include"),
                    str(ROOT / "src/chaos_protocol.c"),
                    str(ROOT / "src/chaos_io.c"),
                    str(ROOT / "tests/chaos/io_harness.c"),
                    "-o",
                    str(cls.exe),
                ],
                check=True,
            )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.run_dir = tempfile.TemporaryDirectory(prefix="chaos-io-")
        self.path = pathlib.Path(self.run_dir.name)

    def tearDown(self):
        self.run_dir.cleanup()

    def execute(self, request=None, mode="normal"):
        self.assertTrue(
            self.exe.exists(), "real engine mailbox/admission implementation is missing"
        )
        if request is not None:
            (self.path / "whisper.json").write_bytes(
                request if isinstance(request, bytes) else json.dumps(request).encode()
            )
        result = subprocess.run(
            [str(self.exe), str(self.path), mode],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        log = self.path / "events.jsonl"
        self.events = []
        # Failure fixtures may be devices or symlinks: never read them.
        if not log.is_symlink() and log.is_file():
            with log.open() as stream:
                text = stream.read(65537)
            self.assertLessEqual(len(text), 65536, "unexpectedly large event log")
            self.events = [json.loads(x) for x in text.splitlines()]
        return json.loads(result.stdout)

    def test_nonfood_only_blocks_hunger(self):
        s = self.execute(
            dict(REQUEST, mutation="hunger_rate", value=2, duration=5, telegraph=3),
            "nonfood",
        )
        self.assertEqual(s["spent"], 0)
        s = self.execute(
            dict(REQUEST, mutation="ward_efficacy", value=50, duration=5, telegraph=2),
            "nonfood",
        )
        self.assertEqual(s["ward"], 1)
        s = self.execute(REQUEST, "nonfood")
        self.assertEqual(s["spent"], 0)
        self.assertEqual(self.events[-1]["cosmetic"], dict(seen=1, last_turn=10))

    def test_empty_mailbox_no_effect(self):
        s = self.execute()
        self.assertEqual(
            (s["spent"], s["ward"], s["hunger"], s["telegraphs"]), (0, 3, 3, 0)
        )
        self.assertEqual(
            [e["event"] for e in self.events], ["safe_point", "safe_point"]
        )

    def test_telegraph_before_real_rule_effect(self):
        r = dict(REQUEST, mutation="ward_efficacy", value=50, duration=5, telegraph=2)
        s = self.execute(r)
        self.assertEqual((s["spent"], s["ward"], s["telegraphs"]), (4, 1, 1))
        self.assertEqual(
            [e["event"] for e in self.events],
            ["safe_point", "telegraph", "ack", "safe_point", "ack"],
        )
        self.assertEqual(
            [e["detail"] for e in self.events if e["event"] == "ack"],
            ["ok", "duplicate"],
        )
        self.assertEqual(
            json.loads((self.path / "whispers.jsonl").read_text())["at"], 1
        )

    def test_frozen_journal_and_ack_bytes(self):
        from chaos.protocol import parse_event

        historical_journal = b'{"v":1,"turn":10,"safe":1,"id":1,"status":"admitted","mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1,"cost":1,"expires":0}\n'
        historical_ack = b'{"v":1,"seq":3,"turn":10,"safe":1,"event":"ack","phase":"result","detail":"ok","sanity":0,"insight":0,"budget":11,"spent":1,"reserved":0,"last_id":1,"vitals":{"hp":0,"hp_max":0,"power":0,"power_max":0},"id":1,"status":"accepted","mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1,"cost":1,"expires":0}'
        self.assertEqual(json.loads(historical_journal)["cost"], 1)
        self.assertEqual(parse_event(historical_ack)["spent"], 1)

    def test_current_journal_and_ack_bytes(self):
        self.execute(REQUEST)
        self.assertEqual(
            (self.path / "whispers.jsonl").read_bytes(),
            b'{"v":1,"policy":2,"turn":10,"safe":1,"id":1,"status":"admitted","mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1,"cost":0,"cosmetic_cost":1,"expires":0}\n',
        )
        self.assertEqual(
            (self.path / "events.jsonl").read_bytes().splitlines()[2],
            b'{"v":3,"seq":3,"turn":10,"safe":1,"event":"ack","phase":"result","detail":"ok","sanity":0,"insight":0,"budget":12,"spent":0,"reserved":0,"last_id":1,"vitals":{"hp":0,"hp_max":0,"power":0,"power_max":0},"cosmetic":{"seen":1,"last_turn":10},"id":1,"status":"accepted","mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1,"cost":0,"cosmetic_cost":1,"expires":0}',
        )

    def test_hunger_rule_and_expiry(self):
        s = self.execute(
            dict(REQUEST, mutation="hunger_rate", value=2, duration=1, telegraph=3),
            "expire",
        )
        self.assertEqual((s["spent"], s["hunger"], s["reserved"]), (3, 3, 0))
        self.assertTrue(any(e["event"] == "expiry" for e in self.events))

    def test_malformed_never_telegraphs(self):
        s = self.execute(b'{"v":1}')
        self.assertEqual(s["telegraphs"], 0)
        self.assertEqual(self.events[-1]["detail"], "schema")

    def test_future_is_pending_then_applies_once(self):
        s = self.execute(dict(REQUEST, at=2))
        self.assertEqual((s["spent"], s["telegraphs"], s["last_id"]), (0, 1, 1))
        self.assertEqual(self.events[-1]["status"], "accepted")

    def test_missed_index_rejects_without_retiming(self):
        s = self.execute(REQUEST, "late")
        self.assertEqual((s["spent"], s["telegraphs"], s["last_id"]), (0, 0, 1))
        self.assertEqual(
            [e["detail"] for e in self.events if e["event"] == "ack"],
            ["schedule", "duplicate"],
        )
        self.assertEqual((self.path / "whispers.jsonl").read_bytes(), b"")

    def test_budget_and_ineligible(self):
        for mode, reason in [("poor", "budget"), ("ineligible", "ineligible")]:
            with self.subTest(mode=mode):
                s = self.execute(
                    dict(
                        REQUEST,
                        mutation="hunger_rate",
                        value=2,
                        duration=5,
                        telegraph=3,
                    ),
                    mode,
                )
                self.assertEqual(s["telegraphs"], 0)
                self.assertIn(reason, [e["detail"] for e in self.events])

    def test_journal_failure_is_fail_closed(self):
        (self.path / "whispers.jsonl").mkdir()
        s = self.execute(REQUEST)
        self.assertEqual((s["spent"], s["telegraphs"]), (0, 0))

    def test_event_failure_is_fail_closed(self):
        os.symlink("/dev/full", self.path / "events.jsonl")
        s = self.execute(REQUEST, "noevents")
        self.assertEqual((s["spent"], s["telegraphs"]), (0, 0))

    def test_mailbox_symlink_rejected(self):
        target = self.path / "other"
        target.write_text(json.dumps(REQUEST))
        (self.path / "whisper.json").symlink_to(target)
        s = self.execute()
        self.assertEqual(s["spent"], 0)

    def test_reentrant_poll_is_ignored(self):
        s = self.execute(REQUEST, "reentrant")
        self.assertEqual((s["safe"], s["spent"], s["telegraphs"]), (2, 0, 1))

    def test_telegraph_failure_is_fail_closed(self):
        s = self.execute(dict(REQUEST, at=2), "fail_ui")
        self.assertEqual(s["spent"], 0)
        self.assertEqual(s["last_id"], 1)

    def test_restore_active_and_pending(self):
        s = self.execute(
            dict(REQUEST, mutation="ward_efficacy", value=50, duration=5, telegraph=2),
            "restore",
        )
        self.assertEqual((s["spent"], s["ward"], s["telegraphs"]), (4, 1, 1))
        self.assertEqual(self.events[-1]["detail"], "duplicate")
