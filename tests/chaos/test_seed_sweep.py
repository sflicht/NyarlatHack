"""Seed sweep (#167): screen model, funnel classification, reproducibility."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import sweep_funnel
import sweep_player
from sweep_screen import Screen, status

ROOT = Path(__file__).resolve().parents[2]


class ScreenTest(unittest.TestCase):
    def test_cursor_motion_erase_and_status(self):
        s = Screen()
        s.feed(b"\x1b[2J\x1b[3;5H@\x1b[1;1Hhello\x1b[K")
        s.feed(b"\x1b[24;1HDlvl:3  $:0  HP:7(13) Pw:9(9) AC:7 T:412 Hungry")
        self.assertEqual(s.rows[2][4], "@")
        self.assertEqual(s.line(0).rstrip(), "hello")
        self.assertEqual(
            status(s),
            {"dlvl": 3, "hp": 7, "hp_max": 13, "turn": 412, "hunger": "Hungry"},
        )

    def test_utf8_split_across_feeds(self):
        s = Screen()
        data = "\x1b[5;1H\u00b6".encode()
        s.feed(data[:-1])
        s.feed(data[-1:])
        self.assertEqual(s.rows[4][0], "\u00b6")

    def test_no_status_line(self):
        self.assertIsNone(status(Screen()))


def _obs(seq, op, stage, root, fact=None, turn=1):
    o = {"operation": op, "stage": stage, "root_seq": root}
    if fact:
        o["fact"] = fact
    return {"event": "observation", "seq": seq, "turn": turn, "observation": o}


def _run(
    tmp, events, envelope=None, schedule=(), director=(), receipts=(), journal=None
):
    run = Path(tmp) / "run"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    if schedule:
        (run / "next_use-schedule.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in schedule)
        )
    if envelope is not None:
        (run / "next_use-envelope.json").write_text(json.dumps(envelope))
    if receipts:
        (run / "next_use-receipt.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in receipts)
        )
    if journal is not None:
        (run / "next_use-journal.jsonl").write_text(journal)
    (run / "director.log").write_text(
        "".join(f"chaos: next-use: {d}\n" for d in director)
    )
    return Path(tmp)


SESSION = {
    "event": "session",
    "seq": 1,
    "turn": 1,
    "budget": 2,
    "sanity": 100,
    "detail": "new",
}


def _whistle(root, fact, turn):
    return [
        _obs(root, "whistling", "started", root, turn=turn),
        _obs(root + 1, "whistling", "notice", root, fact, turn=turn),
        _obs(root + 2, "whistling", "completed", root, turn=turn),
    ]


class FunnelTest(unittest.TestCase):
    def analyse(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            return sweep_funnel.analyse(_run(tmp, **kw))

    def test_no_qualifying_action(self):
        a = self.analyse(events=[SESSION])
        self.assertEqual(a["loss"], "no_qualifying_action")
        self.assertEqual(a["counts"]["qualifying_history"], 0)

    def test_non_qualifying_notice_does_not_count(self):
        a = self.analyse(events=[SESSION, *_whistle(2, "sound_nothing", 5)])
        self.assertEqual(a["qualifying_actions"]["whistling"], 1)
        self.assertEqual(a["counts"]["qualifying_history"], 0)

    def test_candidate_without_publication(self):
        a = self.analyse(
            events=[SESSION, *_whistle(2, "sound_high", 5)],
            schedule=[{"row": 1}],
            director=["pending", "abstained"],
        )
        self.assertEqual(a["counts"]["candidate"], 1)
        self.assertEqual(a["loss"], "director_abstained")

    def _published(self, safe_turn, detail="pray"):
        envelope = {
            "at": 2,
            "cost": 1,
            "origin_refs": [{"end_seq": 4}],
        }
        events = [
            SESSION,
            {
                "event": "safe_point",
                "seq": 2,
                "safe": 1,
                "turn": 1,
                "detail": "level_enter",
                "budget": 2,
            },
            *_whistle(2, "sound_high", 20),
            {
                "event": "safe_point",
                "seq": 9,
                "safe": 2,
                "turn": safe_turn,
                "detail": detail,
                "budget": 2,
            },
        ]
        return self.analyse(events=events, envelope=envelope, schedule=[{"row": 1}])

    def test_published_origin_expired_before_safe_point(self):
        a = self._published(safe_turn=500)
        self.assertEqual(a["counts"]["published"], 1)
        self.assertEqual(a["loss"], "inferred:origin_expired_before_safe_point")

    def test_published_level_changed(self):
        a = self._published(safe_turn=30, detail="level_enter")
        self.assertEqual(a["loss"], "inferred:level_changed_before_safe_point")

    def test_published_origin_superseded(self):
        envelope = {
            "at": 2,
            "cost": 1,
            "origin_refs": [{"end_seq": 4, "family": "W"}],
        }
        safe = {
            "event": "safe_point",
            "seq": 20,
            "safe": 2,
            "turn": 30,
            "detail": "pray",
            "budget": 2,
        }
        events = [
            SESSION,
            *_whistle(2, "sound_high", 20),
            *_whistle(10, "sound_shrill", 25),
            safe,
        ]
        a = self.analyse(events=events, envelope=envelope, schedule=[{"row": 1}])
        self.assertEqual(a["loss"], "inferred:origin_superseded_before_safe_point")

    def test_published_later_origin_expired(self):
        envelope = {
            "at": 2,
            "cost": 1,
            "origin_refs": [
                {"end_seq": 12, "family": "F"},
                {"end_seq": 4, "family": "W"},
            ],
        }
        events = [
            SESSION,
            *_whistle(2, "sound_high", 20),
            {"event": "observation", "seq": 12, "turn": 140, "observation": {}},
            {
                "event": "safe_point",
                "seq": 20,
                "safe": 2,
                "turn": 150,
                "detail": "pray",
                "budget": 2,
            },
        ]
        a = self.analyse(events=events, envelope=envelope, schedule=[{"row": 1}])
        self.assertEqual(a["loss"], "inferred:origin_expired_before_safe_point")

    # Admitted games: later stages come only from the journal.
    ADMITTED = dict(
        events=[SESSION, *_whistle(2, "sound_high", 5)],
        envelope={"at": 2, "cost": 1, "origin_refs": [{"end_seq": 4}]},
        schedule=[{"row": 1}],
        receipts=[{"kind": 2}],
    )

    def _decoded(self, status, private):
        records = [
            {"kind": "transition", "data": {"private_records": private}},
        ]
        return {"status": status, "records": records}

    def _admitted(self, decoded=None, journal=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = _run(tmp, journal=journal, **self.ADMITTED)
            if decoded is None:
                return sweep_funnel.analyse(root)
            with mock.patch.object(sweep_funnel, "read_journal", return_value=decoded):
                return sweep_funnel.analyse(root)

    def test_admitted_journal_missing_is_unknown(self):
        a = self._admitted()
        self.assertEqual(a["counts"]["admitted"], 1)
        self.assertFalse(a["delivery_known"])
        self.assertEqual(a["loss"], "admitted_trace_missing")

    def test_admitted_journal_invalid_is_unknown(self):
        a = self._admitted(journal='{"payload":{"v":1\n')
        self.assertTrue(a["journal_status"].startswith("invalid"))
        self.assertFalse(a["delivery_known"])
        self.assertEqual(a["loss"], "admitted_trace_invalid")

    def test_admitted_journal_incomplete_is_unknown(self):
        a = self._admitted(self._decoded("incomplete", []), journal="x\n")
        self.assertFalse(a["delivery_known"])
        self.assertEqual(a["loss"], "admitted_trace_incomplete")

    def test_incomplete_journal_with_delivery_is_known(self):
        private = [
            {"kind": 2, "at_move": 9, "data": {}},
            {"kind": 3, "at_move": 12, "data": {}},
            {"kind": 4, "at_move": 12, "data": {"outcome": 1}},
            {"kind": 4, "at_move": 15, "data": {"outcome": 3}},
        ]
        a = self._admitted(self._decoded("incomplete", private), journal="x\n")
        self.assertTrue(a["delivery_known"])
        self.assertEqual(a["counts"]["trigger"], 1)
        self.assertEqual(a["counts"]["native_effect"], 1)
        self.assertEqual(a["counts"]["delivered"], 1)
        self.assertIsNone(a["loss"])

    def test_complete_journal_capture_suppressed(self):
        private = [
            {"kind": 2, "at_move": 14, "data": {}},
            {"kind": 4, "at_move": 18, "data": {"outcome": 2}},
            {"kind": 5, "at_move": 18, "data": {"reason": 1}},
        ]
        a = self._admitted(
            self._decoded("structurally_complete", private), journal="x\n"
        )
        self.assertTrue(a["delivery_known"])
        self.assertEqual(a["counts"]["trigger"], 0)
        self.assertEqual(a["loss"], "admitted_no_trigger:whistle_capture_suppressed")

    def test_complete_journal_no_trigger_termination(self):
        private = [
            {"kind": 2, "at_move": 14, "data": {}},
            {"kind": 5, "at_move": 60, "data": {"reason": 4}},
        ]
        a = self._admitted(
            self._decoded("structurally_complete", private), journal="x\n"
        )
        self.assertEqual(a["loss"], "admitted_no_trigger:origin_expired")

    def test_published_no_safe_point(self):
        envelope = {"at": 7, "cost": 1, "origin_refs": [{"end_seq": 4}]}
        a = self.analyse(
            events=[SESSION, *_whistle(2, "sound_high", 20)],
            envelope=envelope,
            schedule=[{"row": 1}],
        )
        self.assertEqual(a["loss"], "inferred:no_safe_point_before_game_end")


class _FakeGame:
    """A live game whose status line never becomes readable."""

    def __init__(self):
        self.raw = bytearray(b"\x1b[2J garbled")
        self.sent = 0

    def send(self, keys):
        self.sent += 1
        return ""


class PlayerBoundTest(unittest.TestCase):
    def test_unreadable_status_is_bounded(self):
        p = sweep_player.Player.__new__(sweep_player.Player)
        p.params = sweep_player.POLICIES["baseline-v1"]
        p.game, p.screen, p.fed = _FakeGame(), Screen(), 0
        p.commands, p.status_misses = 0, 0
        p.settle = lambda text: None
        p.exited = lambda: False
        with self.assertRaises(sweep_player.HarnessError):
            for _ in range(1000):
                p.step()
        self.assertEqual(p.status_misses, sweep_player.MAX_STATUS_MISSES + 1)
        self.assertEqual(p.game.sent, sweep_player.MAX_STATUS_MISSES)
        self.assertEqual(p.commands, sweep_player.MAX_STATUS_MISSES + 1)


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class ReproducibleSweepTest(unittest.TestCase):
    def test_same_seeds_same_report(self):
        digests = []
        with tempfile.TemporaryDirectory() as tmp:
            for k in range(2):
                out = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts/seed_sweep.py"),
                        "--seeds",
                        "1-1",
                        "--starts",
                        "bard",
                        "--jobs",
                        "1",
                        *(["--work", f"{tmp}/w{k}"] if k == 0 else []),
                        "--out",
                        f"{tmp}/r{k}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=True,
                    env=dict(os.environ, TMPDIR=tmp),
                ).stdout
                digests.append(
                    next(s for s in out.splitlines() if s.startswith("REPORT_SHA256="))
                )
        self.assertEqual(digests[0], digests[1])


if __name__ == "__main__":
    unittest.main()
