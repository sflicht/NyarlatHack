"""Synthetic sensitivity probes; NOT native gameplay evidence."""

import copy
from pathlib import Path
import re
import unittest
import test_history_gameplay as subject


class HungerOracleTests(unittest.TestCase):
    def fixture(self):
        request = dict(
            v=1, id=1, mutation="hunger_rate", value=2, duration=10, telegraph=3, at=3
        )
        ack = dict(
            request,
            event="ack",
            phase="result",
            detail="ok",
            status="accepted",
            turn=10,
            expires=20,
            seq=30,
            safe=3,
            cost=3,
            spent=3,
            reserved=3,
            last_id=1,
        )
        expiry = dict(
            v=1,
            event="expiry",
            phase="result",
            detail="hunger_rate",
            turn=21,
            seq=40,
            safe=3,
            spent=3,
            reserved=0,
            last_id=1,
        )
        rows = []
        food = capacity = 0
        # Same turn BEFORE and AFTER ACK, plus elapsed but not yet emitted expiry.
        for call, (turn, seq) in enumerate(
            ((10, 29), (10, 30), (19, 39), (20, 39), (21, 40)), 1
        ):
            admitted, cleared = seq >= 30, seq >= 40
            state = dict(
                event_seq=seq,
                last_id=int(admitted),
                spent=3 * admitted,
                reserved=3 * (admitted and not cleared),
                effect_value=2 * (admitted and not cleared),
                effect_expires=20 * (admitted and not cleared),
                safe=3,
            )
            amount = 2 if admitted and turn < 20 else 1
            food += 1
            rows.append(
                dict(
                    kind="food",
                    call=food,
                    scope=call,
                    turn=turn,
                    before=900,
                    after=900,
                    input=1,
                    output=amount,
                    real_calls=food,
                    **state,
                )
            )
            if turn % 2:
                capacity += 1
                rows.append(
                    dict(
                        kind="capacity",
                        call=capacity,
                        scope=call,
                        turn=turn,
                        result=0,
                        real_calls=capacity,
                    )
                )
            flags = dict.fromkeys(
                (
                    "artifact",
                    "gluttony",
                    "clear_thoughts",
                    "regen_hurt",
                    "regen_mask",
                    "hunger",
                    "ahazu",
                    "conflict",
                    "fast_ring",
                    "left_ring",
                    "right_ring",
                    "amulet",
                    "yendor",
                ),
                0,
            )
            rows.append(
                dict(
                    kind="hungry",
                    call=call,
                    turn=turn,
                    end_turn=turn,
                    before=900,
                    after=900 - amount,
                    count=1,
                    input_sum=1,
                    output_sum=amount,
                    real_calls=call,
                    ordinary=1,
                    insanity=0,
                    nightmare_sanity=100,
                    capacity_count=turn % 2,
                    **flags,
                    **state,
                )
            )
        return rows, request, ack, expiry

    def test_same_turn_order_and_delayed_expiry(self):
        self.assertEqual(
            subject.check_hunger(*self.fixture())["phases"],
            {"before": 1, "during": 2, "after": 2},
        )

    def test_nonzero_native_sources(self):
        rows, req, ack, expiry = self.fixture()
        first = rows[1]
        first.update(
            artifact=1,
            hunger=1,
            conflict=1,
            fast_ring=1,
            gluttony=1,
            insanity=63,
            nightmare_sanity=37,
        )
        # turn10: artifact9 + gluttony2+remainder1 + three even drains.
        first["after"] -= 15
        self.assertEqual(
            subject.check_hunger(rows, req, ack, expiry)["additional_loss"], 15
        )

    def test_odd_capacity_uses_observed_first_return(self):
        rows, req, ack, expiry = self.fixture()
        cap = next(r for r in rows if r["kind"] == "capacity")
        cap["result"] = 2
        hungry = next(r for r in rows if r["kind"] == "hungry" and r["turn"] == 19)
        hungry["after"] -= 1
        self.assertEqual(
            subject.check_hunger(rows, req, ack, expiry)["additional_loss"], 1
        )
        cap["result"] = 1
        with self.assertRaises(ValueError):
            subject.check_hunger(rows, req, ack, expiry)

    def test_zero_ordinary_call_is_retained(self):
        rows, req, ack, expiry = self.fixture()
        rows.pop(2)
        rows[2].update(count=0, input_sum=0, output_sum=0, after=900)
        for row in rows[3:]:
            if row["kind"] == "food":
                row["call"] -= 1
                row["real_calls"] -= 1
        self.assertEqual(subject.check_hunger(rows, req, ack, expiry)["food_calls"], 4)

    def test_control_full_reconciliation(self):
        rows, _, _, _ = self.fixture()
        for row in rows:
            if row["kind"] == "capacity":
                continue
            row.update(last_id=0, spent=0, reserved=0, effect_value=0, effect_expires=0)
            if row["kind"] == "food":
                row["output"] = 1
            else:
                row.update(output_sum=1, after=899)
        self.assertEqual(subject.check_control(rows)["total_loss"], 5)
        rows[1]["after"] -= 1
        with self.assertRaises(ValueError):
            subject.check_control(rows)

    def test_sensitivity(self):
        for name in (
            "loss",
            "flag",
            "missing",
            "bool",
            "expiry_kind",
            "expiry_phase",
            "expiry_early",
            "ack_cost",
            "ack_safe",
            "ack_v",
            "refund",
            "reserved",
            "active_before",
            "inactive_during",
            "capacity_count",
            "scope",
            "no_during",
            "counter",
            "ineligible",
            "ack_spent",
            "expiry_refund",
        ):
            with self.subTest(name=name):
                rows, req, ack, expiry = copy.deepcopy(self.fixture())
                if name == "loss":
                    rows[1]["after"] -= 1
                if name == "flag":
                    rows[1]["hunger"] = 1
                if name == "missing":
                    del rows[1]["hunger"]
                if name == "bool":
                    rows[1]["hunger"] = True
                if name == "expiry_kind":
                    expiry["detail"] = "ward_efficacy"
                if name == "expiry_phase":
                    expiry["phase"] = "attempt"
                if name == "expiry_early":
                    expiry["turn"] = 19
                if name == "ack_cost":
                    ack["cost"] = 2
                if name == "ack_safe":
                    ack["safe"] = 2
                if name == "ack_v":
                    ack["v"] = 2
                if name == "refund":
                    rows[-1]["spent"] = 0
                if name == "reserved":
                    rows[-1]["reserved"] = 3
                if name == "active_before":
                    rows[0]["effect_value"] = 2
                if name == "inactive_during":
                    rows[2]["effect_value"] = 0
                if name == "capacity_count":
                    rows[-1]["capacity_count"] = 0
                if name == "scope":
                    rows[0]["scope"] = 0
                if name == "counter":
                    rows[0]["real_calls"] = 2
                if name == "ineligible":
                    rows[1]["ordinary"] = 0
                if name == "ack_spent":
                    ack["spent"] = 0
                if name == "expiry_refund":
                    expiry["spent"] = 0
                if name == "no_during":
                    rows = [r for r in rows if r["turn"] not in (10, 19)]
                with self.assertRaises(ValueError):
                    subject.check_hunger(rows, req, ack, expiry)

    def test_all_native_extra_branches(self):
        base = self.fixture()[0][1]
        cases = (
            (4, {"left_ring": 1}, 1),
            (12, {"right_ring": 1}, 1),
            (8, {"amulet": 1}, 1),
            (16, {"yendor": 1}, 1),
            (3, {"regen_hurt": 1}, 1),
            (3, {"regen_mask": 2}, 1),
            (3, {"regen_hurt": 1, "regen_mask": 2}, 1),
            (10, {"ahazu": 1}, 0),
            (11, {"ahazu": 1}, 0),
            (10, {"artifact": 1, "count": 0}, 0),
            (
                10,
                {
                    "gluttony": 1,
                    "insanity": 63,
                    "nightmare_sanity": 37,
                    "clear_thoughts": 1,
                },
                0,
            ),
        )
        for turn, flags, expected in cases:
            with self.subTest(turn=turn, flags=flags):
                row = dict(base, turn=turn, capacity_count=turn % 2)
                row.update(flags)
                self.assertEqual(
                    subject._extra(row, [{"result": 0}] if turn % 2 else []), expected
                )

    def test_no_positive_during_sample_rejected(self):
        rows, req, ack, expiry = self.fixture()
        rows = [
            r
            for r in rows
            if not (
                r["kind"] == "food"
                and r["event_seq"] >= ack["seq"]
                and r["turn"] < ack["expires"]
            )
        ]
        call = 0
        for row in rows:
            if row["kind"] == "food":
                call += 1
                row.update(call=call, real_calls=call)
            if (
                row["kind"] == "hungry"
                and row["event_seq"] >= ack["seq"]
                and row["turn"] < 20
            ):
                row.update(count=0, input_sum=0, output_sum=0, after=900)
        with self.assertRaisesRegex(ValueError, "missing positive"):
            subject.check_hunger(rows, req, ack, expiry)

    def test_passive_source_forwards_once(self):
        source = Path(__file__).with_name("history_hunger.c").read_text()
        for name in ("gethungry", "chaos_food", "near_capacity"):
            self.assertEqual(
                len(re.findall(r"__real_" + name + r"\([^;]*\);", source)), 2
            )
        self.assertNotIn("chaos_rule(", source)
        self.assertNotIn("get_uhungersizemod(", source)


if __name__ == "__main__":
    unittest.main()
