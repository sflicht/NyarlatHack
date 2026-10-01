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

    def test_recorded_engine_decision_replaces_inference(self):
        envelope = {"at": 2, "cost": 1, "origin_refs": [{"end_seq": 4}]}
        decision = {
            "next_use_decision_v": 1,
            "decision": "rejected",
            "at": 2,
            "safe": 2,
            "move": 30,
            "reasons": ["level_mismatch", "origin_expired"],
        }
        a = self.analyse(
            events=[SESSION, *_whistle(2, "sound_high", 20)],
            envelope=envelope,
            schedule=[{"row": 1}],
            receipts=[decision],
        )
        self.assertEqual(a["counts"]["admitted"], 0)
        self.assertEqual(a["loss"], "rejected:level_mismatch+origin_expired")
        self.assertEqual(a["recorded_decisions"][0]["safe"], 2)

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
            {"event": "observation", "seq": 12, "turn": 340, "observation": {}},
            {
                "event": "safe_point",
                "seq": 20,
                "safe": 2,
                "turn": 350,
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
        self.assertEqual(a["w_suppressions"], ["unrecorded"])

    def test_capture_suppressed_reports_recorded_reason(self):
        # #196: the loss label is unchanged; the reason is reported beside it.
        for code, name in (
            (1, "none_in_view"),
            (2, "not_eligible"),
            (3, "recheck_failed"),
        ):
            with self.subTest(code=code):
                private = [
                    {"kind": 2, "at_move": 14, "data": {}},
                    {
                        "kind": 4,
                        "at_move": 18,
                        "data": {"outcome": 2, "suppression": code},
                    },
                    {"kind": 5, "at_move": 18, "data": {"reason": 1}},
                ]
                a = self._admitted(
                    self._decoded("structurally_complete", private), journal="x\n"
                )
                self.assertEqual(
                    a["loss"], "admitted_no_trigger:whistle_capture_suppressed"
                )
                self.assertEqual(a["w_suppressions"], [name])

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


class FirstFeltTest(unittest.TestCase):
    """#179: time to the first delivered, on-screen consequence."""

    def _analyse(self, events, journal=None):
        with tempfile.TemporaryDirectory() as tmp:
            return sweep_funnel.analyse(
                _run(tmp, events=events, journal=journal), felt=True
            )

    def test_none_without_consequence(self):
        a = self._analyse([SESSION, *_whistle(2, "sound_high", 5)])
        self.assertIsNone(a["first_felt"])
        self.assertEqual(a["haunt_steps"], 0)

    def test_visible_hound_step_counts(self):
        a = self._analyse(
            [
                SESSION,
                {"event": "haunting", "seq": 2, "turn": 13, "detail": "accepted"},
                {"event": "haunt_step", "seq": 3, "turn": 14, "detail": ""},
                {"event": "haunt_step", "seq": 4, "turn": 15, "detail": ""},
            ]
        )
        self.assertEqual(a["first_felt"], {"turn": 14, "kind": "hound"})
        self.assertEqual(a["haunt"], {"accepted": 1})
        self.assertEqual(a["haunt_steps"], 2)

    def test_whistle_attention_notice_counts_only_when_seen(self):
        def attention(seq, turn, fact):
            return _obs(seq, "whistle_attention", "notice", seq - 1, fact, turn=turn)

        a = self._analyse([SESSION, attention(3, 40, "none")])
        self.assertIsNone(a["first_felt"])
        a = self._analyse(
            [SESSION, attention(3, 40, "none"), attention(5, 90, "attention")]
        )
        self.assertEqual(a["first_felt"], {"turn": 90, "kind": "next_use_W"})

    def test_door_resisted_counts_only_while_door_effect_active(self):
        # #1: first_felt "door" is the first resisted notice under an
        # accepted door_reluctance effect; opened notices, resists before the
        # ACK and resists after expiry do not count.
        def door(seq, turn, fact):
            return _obs(seq, "door_open", "notice", seq - 1, fact, turn=turn)

        ack = {
            "event": "ack",
            "seq": 5,
            "turn": 40,
            "detail": "ok",
            "status": "accepted",
            "mutation": "door_reluctance",
            "expires": 100,
        }
        expiry = {"event": "expiry", "seq": 9, "turn": 100, "detail": "door_reluctance"}
        a = self._analyse(
            [SESSION, door(3, 30, "resisted"), ack, door(7, 50, "opened")]
        )
        self.assertIsNone(a["first_felt"])
        a = self._analyse([SESSION, ack, expiry, door(11, 120, "resisted")])
        self.assertIsNone(a["first_felt"])
        a = self._analyse(
            [SESSION, door(3, 30, "resisted"), ack, door(7, 60, "resisted"), expiry]
        )
        self.assertEqual(a["first_felt"], {"turn": 60, "kind": "door"})

    def test_aggregate_counts_door_first_felt(self):
        # #1: a door first_felt must reach the report's by_kind, not vanish.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "seed_sweep_for_test", ROOT / "scripts/seed_sweep.py"
        )
        assert spec is not None and spec.loader is not None
        seed_sweep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(seed_sweep)
        row = {
            "funnel": {
                "first_felt": {"turn": 60, "kind": "door", "dlvl": 2},
                "last_turn": 100,
                "counts": {"admitted": 0, "delivered": 0},
                "haunt": {},
                "haunt_steps": 0,
            },
            "v2": {
                "dlvl_timeline": [(1, 1), (50, 2)],
                "prayers": 0,
                "flees": 0,
                "rests": 0,
                "whistles_found": 0,
            },
            "whistle_in_inventory": False,
        }
        by_kind = seed_sweep.aggregate_v2([row])["first_felt"]["by_kind"]
        self.assertEqual(
            by_kind,
            {"hound": 0, "next_use_W": 0, "next_use_F": 0, "door": 1, "hunger": 0},
        )

    def test_earliest_kind_wins(self):
        a = self._analyse(
            [
                SESSION,
                _obs(3, "whistle_attention", "notice", 2, "attention", turn=50),
                {"event": "haunt_step", "seq": 4, "turn": 60, "detail": ""},
            ]
        )
        self.assertEqual(a["first_felt"]["kind"], "next_use_W")

    def test_v1_shape_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = sweep_funnel.analyse(_run(tmp, events=[SESSION]))
        for key in ("first_felt", "haunt", "haunt_steps"):
            self.assertNotIn(key, a)

    def test_dlvl_at_uses_public_timeline(self):
        timeline = [(1, 1), (326, 2), (700, 3)]
        self.assertEqual(sweep_funnel.dlvl_at(timeline, 1), 1)
        self.assertEqual(sweep_funnel.dlvl_at(timeline, 325), 1)
        self.assertEqual(sweep_funnel.dlvl_at(timeline, 326), 2)
        self.assertEqual(sweep_funnel.dlvl_at(timeline, 9999), 3)
        self.assertIsNone(sweep_funnel.dlvl_at([], 5))


class PolicyVersionTest(unittest.TestCase):
    def test_baseline_v1_parameters_are_frozen(self):
        # The committed v1 reports were produced by exactly these values.
        self.assertEqual(
            sweep_player.POLICIES["baseline-v1"],
            {
                "max_turns": 2000,
                "max_dlvl": 5,
                "max_commands": 8000,
                "stall_commands": 200,
                "no_food_retry_turns": 200,
                "p_whistle": 0.03,
                "p_fountain": 0.25,
                "fountain_quaffs_per_level": 2,
                "min_turns_per_level": 300,
                "p_search": 0.05,
                "p_travel_explore": 0.8,
                "prayer_gap_turns": 1000,
                "save_restore_turn": 700,
            },
        )

    def test_v2_shares_v1_parameters(self):
        v1, v2 = (sweep_player.POLICIES[k] for k in ("baseline-v1", "baseline-v2"))
        self.assertEqual(v2["version"], 2)
        for key, value in v1.items():
            self.assertEqual(v2[key], value, key)

    def test_default_path_start_uses_ordinary_default_launcher(self):
        self.assertEqual(
            sweep_player.START_LAUNCHER["bard-default-path"],
            ["--ordinary", "--max-runtime", "86400"],
        )
        self.assertNotIn("--no-haunt", sweep_player.START_LAUNCHER["bard-default-path"])
        self.assertIn("--no-haunt", sweep_player.LAUNCHER)

    def test_wizard_default_path_start(self):
        self.assertEqual(
            sweep_player.START_LAUNCHER["wizard-default-path"],
            sweep_player.START_LAUNCHER["bard-default-path"],
        )
        opts = dict(
            o.split(":", 1) if ":" in o else (o, True)
            for o in sweep_player.START_OPTIONS["wizard-default-path"].split(",")
        )
        self.assertEqual(
            {k: opts[k] for k in "role race gender align pettype windowtype".split()},
            dict(
                role="Wiz",
                race="human",
                gender="male",
                align="neutral",
                pettype="kitten",
                windowtype="tty",
            ),
        )
        for (
            flag
        ) in "!news !legacy time !splash_screen !perm_invent !autopickup".split():
            self.assertIn(flag, opts)
        self.assertNotIn("descendant", opts)
        self.assertNotIn("inherited", opts)
        _, full = sweep_player._with_options(
            sweep_player.START_OPTIONS["wizard-default-path"]
        )
        self.assertTrue(full.endswith(",!mail"))

    def test_existing_starts_unchanged(self):
        self.assertIsNone(sweep_player.START_OPTIONS["bard"])
        self.assertIsNone(sweep_player.START_OPTIONS["bard-default-path"])
        self.assertEqual(
            set(sweep_player.START_LAUNCHER),
            {"bard-default-path", "wizard-default-path"},
        )


class FleeTest(unittest.TestCase):
    def _player(self, rows):
        p = sweep_player.Player.__new__(sweep_player.Player)
        p.screen = Screen()
        for y, row in rows.items():
            p.screen.rows[y][: len(row)] = list(row)
        return p

    def test_steps_away_from_the_only_monster(self):
        # hero at (2, 5), jackal at (3, 5): the step must end 2+ squares away.
        p = self._player(
            {
                4: "\u00b7\u00b7\u00b7\u00b7",
                5: "\u00b7\u00b7@d",
                6: "\u00b7\u00b7\u00b7\u00b7",
            }
        )
        d = p.flee((2, 5), [(3, 5)])
        dx, dy = sweep_player.DELTA[d]
        self.assertGreaterEqual(max(abs(2 + dx - 3), abs(5 + dy - 5)), 2)

    def test_no_safe_square_means_no_flee(self):
        # walls ('|', '-') everywhere except the monster's square
        p = self._player({4: "---", 5: "|@d", 6: "---"})
        self.assertIsNone(p.flee((1, 5), [(2, 5)]))


class _FakeGame:
    """A live game whose status line never becomes readable."""

    def __init__(self):
        self.raw = bytearray(b"\x1b[2J garbled")
        self.sent = 0

    def send(self, keys):
        self.sent += 1
        return ""


class _VanishedReader(_FakeGame):
    def send(self, keys):
        raise FileNotFoundError("/proc/1/io")


class PlayerExitRaceTest(unittest.TestCase):
    def _player(self, exits_after):
        p = sweep_player.Player.__new__(sweep_player.Player)
        p.game, p.screen, p.fed = _VanishedReader(), Screen(), 0
        p.game.fd = None
        calls = []

        def exited():
            calls.append(1)
            return len(calls) > exits_after

        p.exited = exited
        return p

    def test_launcher_exits_shortly_after_reader(self):
        p = self._player(exits_after=3)
        self.assertEqual(p.send("x"), b"")

    def test_launcher_still_running_is_an_error(self):
        p = self._player(exits_after=10**9)
        with mock.patch.object(sweep_player, "EXIT_WAIT_SECONDS", 0.1):
            with self.assertRaises(FileNotFoundError):
                p.send("x")


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
        self.assertEqual(p.commands, 0)


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
