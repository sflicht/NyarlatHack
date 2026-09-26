"""Seed sweep (#167): screen model, funnel classification, reproducibility."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import sweep_funnel
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


def _run(tmp, events, envelope=None, schedule=(), director=()):
    run = Path(tmp) / "run"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    if schedule:
        (run / "next_use-schedule.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in schedule)
        )
    if envelope is not None:
        (run / "next_use-envelope.json").write_text(json.dumps(envelope))
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
        self.assertEqual(a["loss"], "origin_expired_before_safe_point")

    def test_published_level_changed(self):
        a = self._published(safe_turn=30, detail="level_enter")
        self.assertEqual(a["loss"], "level_changed_before_safe_point")

    def test_published_no_safe_point(self):
        envelope = {"at": 7, "cost": 1, "origin_refs": [{"end_seq": 4}]}
        a = self.analyse(
            events=[SESSION, *_whistle(2, "sound_high", 20)],
            envelope=envelope,
            schedule=[{"row": 1}],
        )
        self.assertEqual(a["loss"], "no_safe_point_before_game_end")


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
                        "--work",
                        f"{tmp}/w{k}",
                        "--out",
                        f"{tmp}/r{k}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=True,
                ).stdout
                digests.append(
                    next(s for s in out.splitlines() if s.startswith("REPORT_SHA256="))
                )
        self.assertEqual(digests[0], digests[1])


if __name__ == "__main__":
    unittest.main()
