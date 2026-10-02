"""M2 metrics, including the retained real-game journals from PR 3."""

import json
from pathlib import Path
import tempfile
import unittest

import sweep_funnel
from test_seed_sweep import _run, SESSION, _obs

ROOT = Path(__file__).resolve().parents[2]


class ProgramFunnelTests(unittest.TestCase):
    def test_real_ordinary_v3_two_program_capture(self):
        from chaos.next_use_journal import read_journals

        root = ROOT / "docs/measurements/next-use-director-m2/ordinary"
        saved = json.loads((root / "result.json").read_text())
        result = sweep_funnel.analyse(root, felt=True)
        # The committed golden predates the arc metric: every saved field is
        # unchanged, and distinct_felt is the only addition (program 1 once).
        distinct = result.pop("distinct_felt")
        self.assertEqual(result, saved["metrics"])
        self.assertEqual(distinct, [{"turn": 9, "kind": "next_use"}])
        self.assertEqual([p["admitted"] for p in result["programs"]], [1, 1, 0])
        self.assertEqual([p["felt"] for p in result["programs"]], [1, 0, 0])
        self.assertEqual(result["session_details"], ["new", "restore"])
        self.assertEqual(saved["restore_record"]["v"], 3)
        self.assertEqual(saved["restore_record"]["m2"], {"enabled": True, "cap": 3})
        self.assertFalse(saved["wizard"])
        self.assertFalse(saved["hand_placed_envelopes"])
        read_journals(
            [root / "run/next_use-journal.jsonl", root / "run/next_use-journal.2.jsonl"]
        )
        terminal = json.loads(
            (root / "run/next_use-lifecycle.jsonl").read_text().splitlines()[0]
        )
        later = json.loads((root / "run/next_use-envelope.2.json").read_text())
        self.assertGreater(later["origin_refs"][0]["end_seq"], terminal["terminal_seq"])

    def test_f_felt_uses_public_root_and_public_turn_not_replay_clock(self):
        with tempfile.TemporaryDirectory() as root:
            p = _run(
                root,
                events=[
                    SESSION,
                    _obs(2, "fountain_drink", "begin", 2, turn=20),
                    _obs(3, "fountain_drink", "notice", 2, "water_refreshed", turn=20),
                    _obs(4, "fountain_drink", "end", 2, turn=20),
                ],
            )
            self.assertEqual(sweep_funnel.analyse(p, felt=True)["felt_events"], [])
            p.joinpath("run/next_use-felt.jsonl").write_text(
                json.dumps(
                    dict(
                        next_use_felt_v=1,
                        program_ordinal=2,
                        program_id=1,
                        family=2,
                        root_seq=2,
                    )
                )
                + "\n"
            )
            got = sweep_funnel.analyse(p, felt=True, timeline=((1, 4),))
            self.assertEqual(
                got["felt_events"],
                [dict(turn=20, dlvl=4, kind="next_use_F", program=2)],
            )
            self.assertEqual(got["programs"][1]["felt"], 1)

    def test_hunger_is_first_Hungry_sample_per_active_effect(self):
        events = [
            SESSION,
            dict(
                event="ack",
                seq=2,
                turn=10,
                status="accepted",
                mutation="hunger_rate",
                expires=20,
            ),
            dict(
                event="ack",
                seq=3,
                turn=30,
                status="accepted",
                mutation="hunger_rate",
                expires=40,
            ),
        ]
        statuses = [
            dict(turn=t, dlvl=2, hunger=h)
            for t, h in [
                (9, "Hungry"),
                (10, ""),
                (12, "Hungry"),
                (13, "Hungry"),
                (20, "Hungry"),
                (29, "Hungry"),
                (30, "Weak"),
                (31, "Hungry"),
                (32, "Hungry"),
            ]
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = sweep_funnel.analyse(
                _run(tmp, events=events),
                felt=True,
                timeline=[(1, 1), (10, 2)],
                statuses=statuses,
            )
        self.assertEqual(
            result["felt_events"],
            [dict(turn=t, dlvl=2, kind="hunger", program=None) for t in (12, 31)],
        )
        self.assertEqual(result["first_felt"], dict(turn=12, kind="hunger"))

    def test_felt_requires_public_notice_not_only_native_effect(self):
        from unittest.mock import patch

        effect = dict(kind=4, at_move=999, data=dict(family=2, outcome=12, root=12))
        traces = {
            1: dict(
                status="structurally_complete",
                records=[
                    dict(
                        kind="header",
                        data=dict(
                            program_ordinal=1,
                            private_records=[dict(kind=2, at_move=1), effect],
                        ),
                    )
                ],
            )
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = _run(tmp, events=[SESSION], journal="fixture")
            with patch.object(sweep_funnel, "read_journal", return_value=traces[1]):
                result = sweep_funnel.analyse(root, felt=True)
                self.assertEqual(result["programs"][0]["delivered"], 1)
                self.assertEqual(result["felt_events"], [])
                (root / "run/next_use-felt.jsonl").write_text(
                    json.dumps(
                        dict(
                            next_use_felt_v=1,
                            program_ordinal=1,
                            program_id=1,
                            family=2,
                            root_seq=12,
                        )
                    )
                    + "\n"
                )
                # Attribution joins public root to ordinal, not the private clock.
                notice = _obs(
                    13, "fountain_drink", "notice", 12, "water_refreshed", turn=50
                )
                (root / "run/events.jsonl").write_text(
                    json.dumps(SESSION) + "\n" + json.dumps(notice) + "\n"
                )
                result = sweep_funnel.analyse(root, felt=True)
                self.assertEqual(
                    result["felt_events"],
                    [dict(turn=50, dlvl=None, kind="next_use_F", program=1)],
                )

    def test_real_game_three_program_fixture_is_not_collapsed_to_program_one(self):
        root = ROOT / "docs/evidence/next-use-program-journals/native/terminal"
        result = sweep_funnel.analyse(root, felt=True)
        self.assertIn("programs", result)
        self.assertEqual([p["program"] for p in result["programs"]], [1, 2, 3])
        self.assertEqual([p["admitted"] for p in result["programs"]], [1, 1, 1])
        self.assertEqual(
            [p["termination"] for p in result["programs"]], ["completed"] * 3
        )
        self.assertEqual([p["felt"] for p in result["programs"]], [0, 0, 0])

    def test_all_public_felt_events_and_v1_shape(self):
        events = [
            SESSION,
            dict(event="haunt_step", seq=2, turn=4, detail=""),
            dict(event="haunt_step", seq=3, turn=5, detail=""),
            dict(
                event="ack",
                seq=4,
                turn=6,
                status="accepted",
                mutation="door_reluctance",
                expires=10,
            ),
            _obs(5, "door_open", "notice", 4, "resisted", turn=7),
            _obs(6, "door_open", "notice", 5, "resisted", turn=8),
            _obs(7, "door_open", "notice", 6, "resisted", turn=10),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = _run(tmp, events=events)
            v1 = sweep_funnel.analyse(root)
            v2 = sweep_funnel.analyse(root, felt=True)
        self.assertNotIn("felt_events", v1)
        self.assertNotIn("programs", v1)
        self.assertEqual(
            [(e["turn"], e["kind"], e["program"]) for e in v2["felt_events"]],
            [
                (4, "hound", None),
                (5, "hound", None),
                (7, "door", None),
                (8, "door", None),
            ],
        )
