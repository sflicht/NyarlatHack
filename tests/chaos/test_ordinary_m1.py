"""#1 M1: the ordinary default whisper menu (Sam, 2026-09-30).

DL1 arrival: the arrival omen only, so the hound keeps first claim on the
opening budget. From the next level on: a seeded choice among ward_efficacy,
hunger_rate and door_reluctance, each under its own eligibility, cost and
bounds; the omen is not on that menu. No model call anywhere.
"""

import ctypes as C
from pathlib import Path
import tempfile
import unittest

from chaos._protocol_contract import MUTATIONS
from chaos.director import OMEN, OrdinaryBackend, RandomBackend, State
from test_director import current_ack, current_event as event
from test_protocol_contract import Request, compile_core, state_type

ROOT = Path(__file__).resolve().parents[2]
MECHANICAL = {"ward_efficacy", "hunger_rate", "door_reluctance"}


def dl1_opening(budget=2):
    """Fresh game through the DL1 arrival safe point and its accepted omen."""
    return [
        event(1, turn=1, safe=0, event="session", detail="new", budget=budget),
        event(2, turn=1, safe=0, event="level_enter", detail="", budget=budget),
        event(3, turn=1, safe=1, detail="level_enter", budget=budget),
        event(
            4,
            turn=1,
            safe=1,
            event="telegraph",
            detail="ambient",
            last_id=1,
            budget=budget,
        ),
        current_ack(5, OMEN, turn=1, safe=1, budget=budget, spent=0),
    ]


def dl2_arrival(seq=6, *, sanity=100, budget=2, turn=40):
    return [
        event(
            seq,
            turn=turn,
            safe=1,
            event="level_enter",
            detail="",
            sanity=sanity,
            budget=budget,
            last_id=1,
            cosmetic=dict(seen=1, last_turn=1),
        ),
        event(
            seq + 1,
            turn=turn,
            safe=2,
            detail="level_enter",
            sanity=sanity,
            budget=budget,
            last_id=1,
            cosmetic=dict(seen=1, last_turn=1),
        ),
    ]


def state_of(rows):
    s = State()
    for r in rows:
        s.ingest(r)
    return s


class OrdinaryMenuTests(unittest.TestCase):
    def test_dl1_arrival_is_the_omen_only(self):
        fresh = State()
        for seed in range(20):
            backend = OrdinaryBackend(seed)
            self.assertEqual(backend.next(fresh), OMEN)
            self.assertIsNone(backend.choose(fresh, 1, 1))
        # After the omen, nothing mechanical anywhere on DL1, whatever the
        # budget or Sanity (door would qualify at full Sanity with budget 2).
        for budget, sanity in ((2, 100), (12, 0)):
            rows = dl1_opening(budget)
            rows.append(
                event(
                    6,
                    turn=30,
                    safe=2,
                    detail="pray",
                    budget=budget,
                    sanity=sanity,
                    last_id=1,
                    cosmetic=dict(seen=1, last_turn=1),
                )
            )
            s = state_of(rows)
            self.assertEqual(s.level_entries, 1)
            for seed in range(20):
                backend = OrdinaryBackend(seed)
                self.assertIsNone(backend.next(s))
                self.assertEqual(backend.menu(s), {})
                self.assertIsNone(backend.choose(s, 2, 3))

    def test_dl2_arrival_can_yield_door_at_full_sanity(self):
        s = state_of(dl1_opening() + dl2_arrival())
        self.assertEqual(s.level_entries, 2)
        backend = OrdinaryBackend(0)
        self.assertIsNone(backend.next(s))
        self.assertEqual(backend.menu(s), {"door_reluctance": [50]})
        for seed in range(20):
            r = OrdinaryBackend(seed).choose(s, 2, 3)
            self.assertEqual(
                {k: r[k] for k in ("id", "at", "mutation", "value", "telegraph")},
                dict(id=2, at=3, mutation="door_reluctance", value=50, telegraph=4),
            )
            self.assertTrue(1 <= r["duration"] <= 300)

    def test_dl2_menu_is_mechanical_only_with_own_gates(self):
        # Sanity 0 with budget: every mechanical kind qualifies; the omen,
        # though eligible, is never offered past DL1.
        s = state_of(dl1_opening(12) + dl2_arrival(sanity=0, budget=12, turn=60))
        self.assertEqual(set(OrdinaryBackend(0).menu(s)), MECHANICAL)
        picks = {
            OrdinaryBackend(seed).choose(s, 2, 3)["mutation"] for seed in range(40)
        }
        self.assertEqual(picks, MECHANICAL)
        for seed in range(40):
            r = OrdinaryBackend(seed).choose(s, 2, 3)
            lo, hi = MUTATIONS[r["mutation"]]["duration"]
            self.assertTrue(lo <= r["duration"] <= hi, r)
        # Budget 0: nothing, rather than the omen.
        s = state_of(dl1_opening(0) + dl2_arrival(budget=0))
        self.assertEqual(OrdinaryBackend(0).menu(s), {})
        self.assertIsNone(OrdinaryBackend(0).choose(s, 2, 3))

    def test_choice_is_a_pure_function_of_seed_and_slot(self):
        s = state_of(dl1_opening(12) + dl2_arrival(sanity=0, budget=12, turn=60))
        a = [OrdinaryBackend(7).choose(s, 2, n) for n in range(3, 9)]
        backend = OrdinaryBackend(7)
        backend.choose(s, 5, 5)  # an unrelated earlier call changes nothing
        self.assertEqual([backend.choose(s, 2, n) for n in range(3, 9)], a)
        self.assertNotEqual(
            [OrdinaryBackend(8).choose(s, 2, n) for n in range(3, 9)], a
        )


class HoundFirstClaimTests(unittest.TestCase):
    """Regression for the #1 budget probe: a DL1 door would pre-empt the hound."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.lib = compile_core(ROOT, Path(cls.tmp.name) / "core.so")
        cls.lib.chaos_budget.argtypes = [C.c_void_p, C.c_int]
        cls.lib.chaos_spend_non_effect.argtypes = [C.c_void_p, C.c_int, C.c_int]
        cls.lib.chaos_pacing_level.argtypes = [C.c_void_p, C.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def arrival(self):
        s = state_type()()
        self.lib.chaos_state_init(C.byref(s))
        s.pacing = 1
        self.lib.chaos_pacing_level(C.byref(s), 1)
        s.safe = 1
        return s

    def admit(self, s, r):
        req = Request(
            1,
            r["id"],
            MUTATIONS[r["mutation"]]["id"],
            r["value"],
            r["duration"],
            r["telegraph"],
            r["at"],
        )
        return self.lib.chaos_admit(C.byref(s), C.byref(req), 1, 100, 2)

    def test_hound_admitted_with_door_on_the_menu(self):
        haunt = 2  # CHAOS_SPEND_HAUNT
        # M1: the DL1 arrival request is the omen; the hound is still paid for.
        s = self.arrival()
        self.assertEqual(OrdinaryBackend(0).next(State()), OMEN)
        self.assertEqual(self.admit(s, OMEN), 0)
        self.assertEqual(self.lib.chaos_spend_non_effect(C.byref(s), 100, haunt), 0)
        self.assertEqual(s.spent, 2)
        # The probe's failure mode stays reproducible: the plain random
        # chooser would send door at DL1, and the hound is then refused.
        door = RandomBackend(0).choose(state_of(dl1_opening()[:3]), 1, 1)
        self.assertEqual(door["mutation"], "door_reluctance")
        s = self.arrival()
        self.assertEqual(self.admit(s, door), 0)
        self.assertEqual(
            self.lib.chaos_spend_non_effect(C.byref(s), 100, haunt), 5
        )  # CHAOS_BUDGET


if __name__ == "__main__":
    unittest.main()
