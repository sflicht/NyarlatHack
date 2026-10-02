"""Arc metric: distinct felt whispers per game, from hand-built felt_events.

Every existing field, and the raw "2+ felt events" figure, stay unchanged;
the distinct count only deduplicates repeated felt events of one source.
"""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import sweep_funnel
from sweep_programs import distinct_felt
from test_seed_sweep import SESSION, _obs, _run

ROOT = Path(__file__).resolve().parents[2]


def ev(turn, kind, program=None):
    return dict(turn=turn, dlvl=1, kind=kind, program=program)


def kinds(rows):
    return [(r["turn"], r["kind"]) for r in rows]


def seed_sweep():
    spec = importlib.util.spec_from_file_location(
        "seed_sweep_for_distinct", ROOT / "scripts/seed_sweep.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DistinctFeltTests(unittest.TestCase):
    def test_empty_game_has_no_sources(self):
        self.assertEqual(distinct_felt([]), [])

    def test_hound_counts_once_at_its_first_visible_step(self):
        rows = [ev(7, "hound"), ev(8, "hound"), ev(40, "hound"), ev(900, "hound")]
        self.assertEqual(kinds(distinct_felt(rows)), [(7, "hound")])

    def test_hound_only_game_is_never_two_distinct(self):
        # Before: 4 raw felt events = "2+ felt". After: 1 distinct source.
        rows = [ev(t, "hound") for t in (5, 6, 9, 12)]
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(len(distinct_felt(rows)), 1)

    def test_each_program_counts_once_whether_w_or_f(self):
        rows = [
            ev(30, "next_use_W", 1),
            ev(31, "next_use_W", 1),
            ev(80, "next_use_F", 2),
            ev(95, "next_use_W", 2),
            ev(140, "next_use_W", 3),
        ]
        self.assertEqual(
            kinds(distinct_felt(rows)),
            [(30, "next_use"), (80, "next_use"), (140, "next_use")],
        )

    def test_multi_program_game_with_hound(self):
        rows = [
            ev(7, "hound"),
            ev(8, "hound"),
            ev(9, "next_use_W", 1),
            ev(50, "next_use_W", 2),
            ev(51, "hound"),
        ]
        got = distinct_felt(rows)
        self.assertEqual(kinds(got), [(7, "hound"), (9, "next_use"), (50, "next_use")])
        self.assertEqual(sum(r["kind"] != "hound" for r in got), 2)

    def test_unattributed_next_use_rows_are_one_source(self):
        # Historical runs have no public ordinal: never inflate them.
        rows = [ev(9, "next_use_W"), ev(60, "next_use_W")]
        self.assertEqual(kinds(distinct_felt(rows)), [(9, "next_use")])

    def test_door_counts_once_per_accepted_effect(self):
        rows = [ev(60, "door"), ev(64, "door"), ev(130, "door"), ev(200, "door")]
        # Two effects, accepted at turns 50 and 120 (live analysis keys).
        got = distinct_felt(rows, [50, 50, 120, 120])
        self.assertEqual(kinds(got), [(60, "door"), (130, "door")])

    def test_door_without_effect_keys_groups_by_duration_cap(self):
        # Post hoc on older reports: one group per 300 turns (contract cap).
        rows = [ev(697, "door"), ev(704, "door"), ev(712, "door"), ev(801, "door")]
        self.assertEqual(kinds(distinct_felt(rows)), [(697, "door")])
        rows = [ev(100, "door"), ev(399, "door"), ev(400, "door"), ev(650, "door")]
        self.assertEqual(kinds(distinct_felt(rows)), [(100, "door"), (400, "door")])

    def test_hunger_counts_once_per_accepted_effect(self):
        rows = [ev(40, "hunger"), ev(90, "hunger")]
        self.assertEqual(len(distinct_felt(rows, [10, 10])), 1)
        self.assertEqual(len(distinct_felt(rows, [10, 60])), 2)
        # Without keys each row is already one window's first Hungry.
        self.assertEqual(len(distinct_felt(rows)), 2)

    def test_order_independent_and_unknown_kind_fails_closed(self):
        rows = [ev(50, "next_use_W", 1), ev(7, "hound"), ev(8, "hound")]
        self.assertEqual(kinds(distinct_felt(rows)), [(7, "hound"), (50, "next_use")])
        with self.assertRaisesRegex(ValueError, "unknown felt kind"):
            distinct_felt([ev(1, "omen")])


class DistinctFeltAnalyseTests(unittest.TestCase):
    """The live analyser keys door effects by their accepted ack."""

    def door_ack(self, seq, turn, expires):
        return dict(
            event="ack",
            seq=seq,
            turn=turn,
            status="accepted",
            mutation="door_reluctance",
            expires=expires,
        )

    def test_two_door_effects_in_one_game(self):
        events = [
            SESSION,
            self.door_ack(2, 10, 40),
            _obs(3, "door_open", "notice", 3, "resisted", turn=12),
            _obs(4, "door_open", "notice", 4, "resisted", turn=15),
            dict(event="expiry", seq=5, turn=40, detail="door_reluctance"),
            self.door_ack(6, 45, 80),
            _obs(7, "door_open", "notice", 7, "resisted", turn=50),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            a = sweep_funnel.analyse(_run(tmp, events=events), felt=True)
        # Existing fields unchanged: three raw door events.
        self.assertEqual([e["kind"] for e in a["felt_events"]], ["door"] * 3)
        self.assertEqual(set(a["felt_events"][0]), {"turn", "dlvl", "kind", "program"})
        self.assertEqual(kinds(a["distinct_felt"]), [(12, "door"), (50, "door")])

    def test_v1_shape_has_no_distinct_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = sweep_funnel.analyse(_run(tmp, events=[SESSION]))
        self.assertNotIn("distinct_felt", a)


class DistinctFeltAggregateTests(unittest.TestCase):
    def row(self, felt):
        return {
            "funnel": {
                "first_felt": None,
                "last_turn": 100,
                "counts": {"admitted": 0, "delivered": 0},
                "haunt": {},
                "haunt_steps": 0,
                "felt_events": felt,
            },
            "v2": {
                "dlvl_timeline": [(1, 1)],
                "prayers": 0,
                "flees": 0,
                "rests": 0,
                "whistles_found": 0,
            },
            "whistle_in_inventory": False,
        }

    def test_per_start_figures_beside_the_raw_figure(self):
        rows = [
            self.row([ev(5, "hound"), ev(6, "hound"), ev(9, "hound")]),  # hound only
            self.row([ev(5, "hound"), ev(30, "next_use_W", 1)]),
            self.row([ev(30, "next_use_W", 1), ev(90, "next_use_W", 2)]),
            self.row([ev(60, "door"), ev(61, "door")]),  # one door effect
            self.row([]),
        ]
        d = seed_sweep().aggregate_v2(rows)["distinct_felt"]
        self.assertEqual(d["games_2plus_raw_felt_events"], 4)
        self.assertEqual(d["games_2plus"], 2)
        self.assertEqual(d["games_2plus_excluding_hound"], 1)
        self.assertEqual(d["per_game"], {0: 1, 1: 2, 2: 2})
        self.assertEqual(
            d["sources_by_kind"], {"hound": 2, "next_use": 3, "door": 1, "hunger": 0}
        )
        self.assertEqual(
            d["games_by_kind"], {"hound": 2, "next_use": 2, "door": 1, "hunger": 0}
        )

    def test_stored_distinct_field_wins_over_post_hoc(self):
        row = self.row([ev(60, "door"), ev(130, "door")])
        row["funnel"]["distinct_felt"] = [
            dict(turn=60, kind="door"),
            dict(turn=130, kind="door"),
        ]
        d = seed_sweep().aggregate_v2([row])["distinct_felt"]
        self.assertEqual(d["games_2plus"], 1)


if __name__ == "__main__":
    unittest.main()
