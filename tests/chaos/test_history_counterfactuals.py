"""Synthetic causal-policy interventions, never modified native provenance."""

import json
import unittest

from chaos.director import eligible
from chaos.history import HistoryState, candidate_requests, public_context
from chaos.history_choice import RandomHistoryBackend
from test_director import ack, event
from test_episodes import action, enabled, session, wire


def action_rows(fact):
    rows = [enabled(), session(2)]
    if fact is not None:
        action(rows, "fountain_drink", fact)
    for row in rows:
        row.update(sanity=60, budget=6)
    return rows


def prior_rows(condition):
    rows = action_rows("water_refreshed")
    request = dict(
        v=1, id=1, at=1, mutation="hunger_rate", value=2, duration=10, telegraph=3
    )
    accepted = condition in ("active", "expired")
    if condition != "absent":
        rows.append(
            ack(
                len(rows) + 1,
                request,
                # Synthetic rejected case is ineligible at high Sanity;
                # the final row then restores ordinary current eligibility.
                sanity=60 if accepted else 100,
                budget=3 if accepted else 2,
                status="accepted" if accepted else "rejected",
                detail="ok" if accepted else "ineligible",
                cost=3,
                spent=3 if accepted else 0,
                reserved=3 if accepted else 0,
                expires=20 if accepted else 0,
            )
        )
    if condition == "expired":
        rows.append(
            event(
                len(rows) + 1,
                event="expiry",
                detail="hunger_rate",
                turn=20,
                sanity=60,
                budget=3,
                spent=3,
                reserved=0,
                last_id=1,
            )
        )
    rows.append(
        event(
            len(rows) + 1,
            turn=15 if condition == "active" else 30,
            sanity=60,
            budget=3 if accepted else 6,
            spent=3 if accepted else 0,
            reserved=3 if condition == "active" else 0,
            last_id=0 if condition == "absent" else 1,
        )
    )
    return rows


class HistoryCounterfactualTests(unittest.TestCase):
    def test_action_axis_fixed_entire_legacy_summary_and_seeds(self):
        states = []
        for fact in (None, "water_foul", "water_refreshed"):
            rows = action_rows(fact)
            rows.append(event(len(rows) + 1, turn=30, sanity=60, budget=6))
            states.append(HistoryState(wire(*rows)))
        summaries = [json.loads(s.summary()) for s in states]
        self.assertEqual(summaries[0], summaries[1])
        self.assertEqual(summaries[0], summaries[2])
        durations = set()
        for index, state in enumerate(states):
            self.assertIn("hunger_rate", eligible(state, True))
            menu = candidate_requests(state, True)
            self.assertEqual(
                [r["duration"] for r in menu], [10, 20] if index == 2 else []
            )
            for seed in (0, 1, 7):
                first = RandomHistoryBackend(seed)
                selected = first.choose(public_context(state), menu)
                self.assertEqual(
                    selected,
                    RandomHistoryBackend(seed).choose(public_context(state), menu),
                )
                self.assertEqual(first.attempts, int(index == 2))
                if selected is not None:
                    durations.add(selected["duration"])
        self.assertEqual(durations, {10, 20})

    def test_prior_axis_fixed_actions_and_expired_ordinary_eligibility(self):
        actions = None
        for condition in ("absent", "rejected", "active", "expired"):
            rows = prior_rows(condition)
            current_actions = [r for r in rows if r["v"] == 2]
            if actions is None:
                actions = current_actions
            self.assertEqual(current_actions, actions)
            state = HistoryState(wire(*rows))
            allowed = condition in ("absent", "rejected")
            self.assertEqual(bool(candidate_requests(state, True)), allowed)
            if condition == "expired":
                self.assertEqual(state.active, {})
                self.assertIn("hunger_rate", eligible(state, True))
                self.assertTrue(state.prior_whispers[0]["expiry_observed"])
            for seed in (0, 1, 7):
                backend = RandomHistoryBackend(seed)
                chosen = backend.choose(
                    public_context(state), candidate_requests(state, True)
                )
                self.assertEqual(chosen is not None, allowed)
                self.assertEqual(backend.attempts, int(allowed))

    def test_restore_with_fresh_refresh_is_suppressed_only_by_prior_acceptance(self):
        for condition in ("absent", "expired"):
            rows = prior_rows(condition)
            values = {
                k: rows[-1][k]
                for k in (
                    "turn",
                    "safe",
                    "sanity",
                    "budget",
                    "spent",
                    "reserved",
                    "last_id",
                )
            }
            rows.append(dict(enabled(len(rows) + 1), **values))
            rows.append(session(len(rows) + 1, "restore", **values))
            start = len(rows)
            action(rows, "fountain_drink", "water_refreshed")
            for row in rows[start:]:
                row.update(values)
            state = HistoryState(wire(*rows))
            self.assertTrue(state.enabled)
            self.assertEqual(state.active, {})
            self.assertIn("hunger_rate", eligible(state, True))
            self.assertTrue(state.episodes["episodes"])
            self.assertEqual(
                bool(candidate_requests(state, True)), condition == "absent"
            )
