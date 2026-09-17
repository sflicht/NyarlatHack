"""Independent synthetic whole streams; not native journey evidence."""

import copy
import importlib.util
import unittest

from test_episodes import enabled, session, action, wire


def historical_stream():
    rows = [enabled(), session(2)]
    action(rows)
    action(rows)
    return rows


def current_stream():
    # Independently declared current envelopes and zero state, never captured data.
    rows = historical_stream()
    for row in rows:
        row["v"] = 4 if row["event"] == "observation" else 3
        row["cosmetic"] = {"seen": 0, "last_turn": 0}
    return rows


class ObservationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("native_observation_contract"),
            "explicit policy helper is missing",
        )
        import native_observation_contract

        self.contract = native_observation_contract

    def test_both_explicit_whole_streams_and_only_seq_projection(self):
        c = self.contract
        for policy, rows in (
            (c.HISTORICAL, historical_stream()),
            (c.CURRENT, current_stream()),
        ):
            c.validate_rows(rows, policy)
            original = copy.deepcopy(rows)
            expected = dict(rows[1], seq=1)
            self.assertEqual(c.ordinary_projection(rows, policy), [expected])
            self.assertEqual(rows, original)
        self.assertEqual(c.validate_rows([], c.CURRENT), [])  # first write failed
        rows = current_stream()
        self.assertEqual(
            c.ordinary_projection(rows, c.CURRENT, renumber_seq=False), [rows[1]]
        )
        with self.assertRaises(AssertionError):
            c.validate_rows(rows, (1, 4))

    def test_foreign_mixed_bool_and_event_kind_rejected(self):
        c = self.contract
        good = current_stream()
        c.validate_rows(good, c.CURRENT)
        for version in (1, 2, True, False, 3, 5, 4.0):
            bad = copy.deepcopy(good)
            bad[0]["v"] = version
            with self.subTest(version=version), self.assertRaises(AssertionError):
                c.validate_rows(bad, c.CURRENT)
        for rows in (historical_stream(), good + historical_stream()):
            with self.assertRaises(AssertionError):
                c.validate_rows(rows, c.CURRENT)
        for field, value in (("event", "session"), ("observation", None)):
            bad = copy.deepcopy(good)
            bad[0][field] = value
            with self.assertRaises(AssertionError):
                c.validate_rows(bad, c.CURRENT)
        bad = copy.deepcopy(good)
        bad[1]["observation"] = {}
        with self.assertRaises(AssertionError):
            c.validate_rows(bad, c.CURRENT)

    def test_cosmetic_exact_shape_types_and_zero_every_row(self):
        c = self.contract
        for index in (0, 1):
            for cosmetic in (
                None,
                {},
                {"seen": 0},
                {"seen": 0, "last_turn": 0, "extra": 0},
                {"seen": False, "last_turn": 0},
                {"seen": 0, "last_turn": False},
                {"seen": 1, "last_turn": 0},
                {"seen": 0, "last_turn": 1},
            ):
                bad = current_stream()
                bad[index]["cosmetic"] = cosmetic
                with (
                    self.subTest(index=index, cosmetic=cosmetic),
                    self.assertRaises(AssertionError),
                ):
                    c.validate_rows(bad, c.CURRENT)
            bad = current_stream()
            del bad[index]["cosmetic"]
            with self.assertRaises(AssertionError):
                c.validate_rows(bad, c.CURRENT)

    def test_nonvacuous_projection_and_semantic_change(self):
        c = self.contract
        good = current_stream()
        expected = c.ordinary_projection(good, c.CURRENT)
        bad = copy.deepcopy(good)
        bad[1]["detail"] = "changed"
        self.assertNotEqual(c.ordinary_projection(bad, c.CURRENT), expected)
        for rows in ([], [r for r in good if r["v"] == 4]):
            with self.assertRaisesRegex(AssertionError, "ordinary"):
                c.ordinary_projection(rows, c.CURRENT)

    def test_delivery_byte_goldens_are_separate_and_exact(self):
        import json
        from test_episode_delivery import WRITE_NOTICE, CURRENT_WRITE_NOTICE

        old, new = json.loads(WRITE_NOTICE), json.loads(CURRENT_WRITE_NOTICE)
        self.contract.validate_rows([old], self.contract.HISTORICAL)
        self.contract.validate_rows([new], self.contract.CURRENT)
        self.assertEqual(list(new)[-3:], ["vitals", "cosmetic", "observation"])
        self.assertEqual(CURRENT_WRITE_NOTICE[:7], b'{"v":4,')
        self.assertEqual(WRITE_NOTICE[:7], b'{"v":2,')
        self.assertNotEqual(CURRENT_WRITE_NOTICE, WRITE_NOTICE)
        self.assertEqual(
            CURRENT_WRITE_NOTICE,
            json.dumps(new, separators=(",", ":")).encode() + b"\n",
        )

    def test_turnloop_current_parity_and_root_semantic_negatives(self):
        from test_episode_turnloop_oracle import compare_current_events

        on = current_stream()
        off = [dict(on[1], seq=1)]
        compare_current_events(wire(*off), wire(*on), ["whistling", "whistling"])
        for mutate, message in (
            (lambda r: r[1].update(detail="changed"), "ordinary parity"),
            (lambda r: r.__delitem__(slice(2, None)), "selected roots"),
        ):
            bad = copy.deepcopy(on)
            mutate(bad)
            with self.assertRaisesRegex(AssertionError, message):
                compare_current_events(
                    wire(*off), wire(*bad), ["whistling", "whistling"]
                )
        with self.assertRaisesRegex(AssertionError, "ordinary"):
            compare_current_events(b"", b"", [])

    def test_action_current_positive_then_root_phase_and_notice_changes(self):
        from test_episode_action_transport import validate_action_observations

        good = current_stream()
        validate_action_observations(wire(*good))
        for index, field, value in (
            (3, "root_seq", 999),
            (3, "fact", "none"),
            (4, "stage", "blocked"),
        ):
            bad = copy.deepcopy(good)
            bad[index]["observation"][field] = value
            with self.assertRaises((AssertionError, ValueError)):
                validate_action_observations(wire(*bad))
        bad = copy.deepcopy(good)
        bad[2]["phase"] = "result"
        with self.assertRaises((AssertionError, ValueError)):
            validate_action_observations(wire(*bad))


if __name__ == "__main__":
    unittest.main()
