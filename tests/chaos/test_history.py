"""Synthetic policy fixtures, not native delivery or application witnesses."""

import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from chaos.director import State
from chaos.episodes import project_episodes
from chaos.protocol import MAX_INT, parse_event
from test_director import ack, event
from test_episodes import action, enabled, session, wire


class HistoryTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("chaos.history"), "history API missing"
        )
        return importlib.import_module("chaos.history")

    def rows(self, fact="water_refreshed", terminal="completed"):
        rows = [enabled(), session(2, private="SECRET")]
        action(rows, "fountain_drink", fact, terminal)
        for row in rows:
            row.update(sanity=70, budget=6)
        return rows

    def state(self, rows):
        return self.api().HistoryState(wire(*rows))

    def admitted(self, name="hunger_rate"):
        rows = self.rows()
        request = dict(
            v=1,
            id=1,
            at=1,
            mutation=name,
            value=2 if name == "hunger_rate" else 1,
            duration=10 if name == "hunger_rate" else 0,
            telegraph=3 if name == "hunger_rate" else 1,
        )
        rows.append(
            ack(
                6,
                request,
                sanity=70,
                cost=3 if name == "hunger_rate" else 1,
                spent=5,
                reserved=3 if name == "hunger_rate" else 0,
                expires=20 if name == "hunger_rate" else 0,
            )
        )
        return rows

    def test_mixed_latest_and_unchanged_legacy(self):
        rows = self.rows()
        rows[-1].update(budget=4, insight=9)
        state = self.state(rows)
        self.assertEqual(state.latest, rows[-1])
        self.assertEqual(state.episodes, project_episodes(wire(*rows)))
        self.assertEqual(json.loads(state.summary())["observed"]["insight"], 9)
        self.assertEqual(state.safe, 1)
        self.assertEqual(state.last_id, 0)
        self.assertTrue(state.enabled)
        for consume in (
            lambda: parse_event(json.dumps(rows[-1])),
            lambda: State().ingest(rows[-1]),
        ):
            with self.assertRaises(ValueError):
                consume()

    def test_exact_policy_and_negative_actions(self):
        api = self.api()
        state = self.state(self.rows())
        expected = [
            dict(
                v=1,
                id=1,
                at=2,
                mutation="hunger_rate",
                value=2,
                duration=d,
                telegraph=3,
            )
            for d in (10, 20)
        ]
        self.assertEqual(api.candidate_requests(state, True), expected)
        self.assertEqual(api.candidate_requests(state), [])
        for bad in (1, "yes", None, []):
            with self.assertRaises(ValueError):
                api.candidate_requests(state, bad)
        for fact, terminal in (
            (None, "completed"),
            ("water_refreshed", None),
            ("water_foul", "completed"),
            ("detection_presented", "completed"),
            ("cannot_reach", "blocked"),
        ):
            self.assertEqual(
                api.candidate_requests(self.state(self.rows(fact, terminal)), True), []
            )
        for kw in (
            dict(sanity=91),
            dict(budget=2),
            dict(event="death", phase="result"),
            dict(last_id=MAX_INT),
            dict(safe=MAX_INT),
        ):
            rows = self.rows()
            rows.append(event(len(rows) + 1, sanity=70, budget=6))
            rows[-1].update(kw)
            self.assertEqual(api.candidate_requests(self.state(rows), True), [])

    def test_all_retained_roots_not_only_presented_evidence(self):
        rows = self.rows("water_foul")
        action(rows, "fountain_drink", "water_foul")
        action(rows, "fountain_drink", "water_refreshed")
        action(rows, "fountain_drink", "water_foul")
        for row in rows:
            row.update(sanity=70, budget=6)
        self.assertTrue(self.api().candidate_requests(self.state(rows), True))
        for _ in range(32):
            action(rows)
        for row in rows:
            row.update(sanity=70, budget=6)
        self.assertEqual(self.api().candidate_requests(self.state(rows), True), [])
        rows[3]["observation"]["root_seq"] = 2
        with self.assertRaises(ValueError):
            self.state(rows)

    def test_prior_admission_expiry_and_restore(self):
        api = self.api()
        rows = self.admitted()
        state = self.state(rows)
        self.assertEqual(api.candidate_requests(state, True), [])
        self.assertEqual(
            state.prior_whispers,
            [
                dict(
                    id=1,
                    mutation="hunger_rate",
                    duration=10,
                    accepted_seq=6,
                    accepted_turn=10,
                    expires_turn=20,
                    active_at_snapshot=True,
                    expiry_observed=False,
                )
            ],
        )
        rows.append(event(7, turn=20, spent=5, last_id=1))
        state = self.state(rows)
        self.assertEqual(state.active, {})
        self.assertFalse(state.prior_whispers[0]["expiry_observed"])
        rows.append(
            event(8, event="expiry", detail="hunger_rate", turn=21, spent=5, last_id=1)
        )
        self.assertTrue(self.state(rows).prior_whispers[0]["expiry_observed"])
        rows.append(session(9, "restore", turn=21, safe=1, spent=5, last_id=1))
        state = self.state(rows)
        self.assertFalse(state.enabled)
        self.assertEqual(state.episodes["episodes"], [])
        self.assertEqual(len(state.accepted), 1)
        self.assertEqual(api.candidate_requests(state, True), [])

    def test_rejection_telegraph_and_ambient_do_not_suppress(self):
        api = self.api()
        for suffix in (
            event(
                6,
                event="telegraph",
                detail="hunger_rate",
                last_id=1,
                sanity=70,
                budget=6,
            ),
            dict(
                self.admitted()[-1],
                status="rejected",
                detail="budget",
                expires=0,
                spent=0,
                reserved=0,
                budget=6,
            ),
        ):
            state = self.state(self.rows() + [suffix])
            self.assertEqual(state.accepted, {})
            self.assertTrue(api.candidate_requests(state, True))
        rows = self.admitted("ambient")
        rows[-1]["budget"] = 5
        self.assertTrue(api.candidate_requests(self.state(rows), True))

    def test_malformed_acceptance_and_expiry(self):
        for kw in (
            dict(cost=1),
            dict(expires=19),
            dict(at=2),
            dict(last_id=2),
            dict(phase="attempt"),
        ):
            rows = self.admitted()
            rows[-1].update(kw)
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.state(rows)
        rows = self.admitted()
        for extra in (
            dict(rows[-1], seq=7, turn=11, expires=21),
            event(7, event="expiry", detail="hunger_rate", turn=19, spent=5, last_id=1),
            event(
                7, event="expiry", detail="ward_efficacy", turn=20, spent=5, last_id=1
            ),
        ):
            with self.assertRaises(ValueError):
                self.state(rows + [extra])
        with self.assertRaises(ValueError):
            self.state(self.rows() + [event(6, event="expiry", detail="hunger_rate")])
        duplicate = dict(
            rows[-1], seq=7, status="rejected", detail="duplicate", expires=0
        )
        self.assertEqual(len(self.state(rows + [duplicate]).accepted), 1)

    def test_partial_schema_caps_and_death(self):
        api = self.api()
        for raw in (b"", wire(*self.rows()) + b'{"v":', wire(*self.rows())[:-1]):
            with self.assertRaises(api.IncompleteHistory):
                api.HistoryState(raw)
        for raw in (
            b"{}\n" + b"{",
            b"x" * 4097,
            b"{}\n",
            wire(enabled()),
            wire(session(), enabled(2)),
            b"{}\n" * 50001 + b"{",
        ):
            with self.assertRaises(ValueError) as caught:
                api.HistoryState(raw)
            self.assertNotIsInstance(caught.exception, api.IncompleteHistory)
        self.assertTrue(self.state([session(), event(2, event="death")]).ended)

    def test_full_admission_memory_outlives_public_window(self):
        api = self.api()
        rows = self.admitted()
        rows.append(
            event(7, event="expiry", detail="hunger_rate", turn=20, spent=5, last_id=1)
        )
        for ident in range(2, 6):
            request = dict(
                v=1,
                id=ident,
                at=ident,
                mutation="ambient",
                value=1,
                duration=0,
                telegraph=1,
            )
            rows.append(
                ack(
                    len(rows) + 1,
                    request,
                    turn=20,
                    safe=ident,
                    last_id=ident,
                    spent=ident + 4,
                    cost=1,
                    expires=0,
                    budget=3,
                    sanity=70,
                )
            )
        state = self.state(rows)
        self.assertEqual(len(state.accepted), 5)
        self.assertEqual(len(state.prior_whispers), 3)
        self.assertEqual(state.prior_coverage, dict(shown=3, omitted=2))
        self.assertEqual(api.candidate_requests(state, True), [])
        self.assertNotIn(
            "hunger_rate", [record["mutation"] for record in state.prior_whispers]
        )

    def test_active_filter_uses_final_mixed_turn(self):
        rows = self.admitted()
        start = len(rows)
        action(rows)
        for row in rows[start:]:
            row.update(turn=21, last_id=1, spent=5, reserved=3)
        state = self.state(rows)
        self.assertEqual(state.active, {})
        self.assertFalse(state.prior_whispers[0]["expiry_observed"])

    def test_restore_enabled_marker_and_boundary_eligibility(self):
        api = self.api()
        rows = self.rows()
        rows.append(dict(enabled(6), safe=1, sanity=70, budget=6))
        rows.append(session(7, "restore", safe=1, sanity=70, budget=6))
        self.assertTrue(self.state(rows).enabled)
        self.assertEqual(api.candidate_requests(self.state(rows), True), [])
        start = len(rows)
        action(rows, "fountain_drink", "water_refreshed")
        for row in rows[start:]:
            row.update(sanity=70, budget=6)
        self.assertTrue(api.candidate_requests(self.state(rows), True))

    def test_snapshot_checkpoint_and_public_privacy(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            raw = wire(*self.rows())
            path.write_bytes(raw)
            path.chmod(0o600)
            state, proof = api.snapshot_history(directory)
            public = api.public_context(state)
            self.assertEqual(
                set(public),
                {
                    "history_context_v",
                    "summary",
                    "episodes",
                    "prior_whispers",
                    "prior_coverage",
                },
            )
            self.assertLessEqual(len(json.dumps(public).encode()), 6144)
            for secret in ("SECRET", "sha256", "identity", directory):
                self.assertNotIn(secret, json.dumps(public))
            path.write_bytes(raw + b"{")
            self.assertEqual(
                api.snapshot_history(directory, checkpoint=copy.deepcopy(proof))[
                    0
                ].latest,
                state.latest,
            )
            with self.assertRaises(api.IncompleteHistory):
                api.snapshot_history(directory)
            path.chmod(0o644)
            with self.assertRaises(ValueError) as caught:
                api.snapshot_history(directory)
            self.assertNotIsInstance(caught.exception, api.IncompleteHistory)
            path.chmod(0o600)
            path.write_bytes(raw.replace(b"SECRET", b"PUBLIC"))
            with self.assertRaises(ValueError):
                api.snapshot_history(directory, checkpoint=proof)
