"""Ordinary OAuth menu contract; synthetic state and stubbed generation only."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from chaos.director import State
from chaos.oauth import OAuthBackend
from chaos.protocol import parse_event


def restored_state(*, seen=1, last=1, turn=51, sanity=100):
    row = dict(
        v=3,
        seq=1,
        turn=turn,
        safe=1,
        event="session",
        phase="result",
        detail="restore",
        sanity=sanity,
        insight=0,
        budget=2 + (100 - sanity) // 10,
        spent=0,
        reserved=0,
        last_id=1,
        cosmetic=dict(seen=seen, last_turn=last),
    )
    state = State()
    state.ingest(parse_event(json.dumps(row)))
    return state


def request(*, value=2, mutation="ambient", ident=2, at=2):
    return dict(
        v=1,
        id=ident,
        at=at,
        mutation=mutation,
        value=value,
        duration=0 if mutation == "ambient" else 1,
        telegraph=1 if mutation == "ambient" else 2,
    )


class OAuthMenuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "never-created.json"
        self.factory = Mock(side_effect=AssertionError("no credential/provider access"))
        self.backend = OAuthBackend(self.ledger, client_factory=self.factory)

    def tearDown(self):
        self.factory.assert_not_called()
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_unused_values_are_supplied_and_accepted(self):
        for value in (2, 3):
            with self.subTest(value=value):
                answer = request(value=value)
                with patch.object(
                    self.backend, "generate", return_value=json.dumps(answer)
                ) as generate:
                    self.assertEqual(
                        self.backend.choose(restored_state(), 2, 2), answer
                    )
                generate.assert_called_once()
                system, raw = generate.call_args.args
                payload = json.loads(raw)
                self.assertIn("allowed_values", system)
                self.assertEqual(payload["eligible"], ["ambient"])
                self.assertEqual(payload["allowed_values"], {"ambient": [2, 3]})
                self.assertEqual(
                    (payload["assigned_id"], payload["assigned_at"]), (2, 2)
                )

    def test_used_ambient_value_is_rejected(self):
        with patch.object(
            self.backend, "generate", return_value=json.dumps(request(value=1))
        ):
            with self.assertRaises(ValueError):
                self.backend.choose(restored_state(), 2, 2)

    def test_mechanical_preference_prompt_and_response(self):
        state = restored_state(sanity=80)
        answer = request(mutation="ward_efficacy", value=50)
        with patch.object(
            self.backend, "generate", return_value=json.dumps(answer)
        ) as generate:
            self.assertEqual(self.backend.choose(state, 2, 2), answer)
        payload = json.loads(generate.call_args.args[1])
        self.assertEqual(payload["eligible"], ["ward_efficacy"])
        self.assertEqual(payload["allowed_values"], {"ward_efficacy": [50]})
        with patch.object(self.backend, "generate", return_value=json.dumps(request())):
            with self.assertRaises(ValueError):
                self.backend.choose(state, 2, 2)

    def test_depletion_and_cooldown_never_generate(self):
        for state in (restored_state(seen=7), restored_state(turn=50)):
            with (
                self.subTest(snapshot=state.latest),
                patch.object(self.backend, "generate") as generate,
            ):
                self.assertIsNone(self.backend.choose(state, 2, 2))
                generate.assert_not_called()

    def test_only_last_unused_value_is_offered(self):
        state = restored_state(seen=3)
        with patch.object(
            self.backend, "generate", return_value=json.dumps(request(value=3))
        ) as generate:
            self.backend.choose(state, 2, 2)
        self.assertEqual(
            json.loads(generate.call_args.args[1])["allowed_values"], {"ambient": [3]}
        )
        with patch.object(
            self.backend, "generate", return_value=json.dumps(request(value=2))
        ):
            with self.assertRaises(ValueError):
                self.backend.choose(state, 2, 2)

    def test_assigned_schedule_checks_remain(self):
        for answer in (request(ident=3), request(at=3)):
            with (
                self.subTest(answer=answer),
                patch.object(self.backend, "generate", return_value=json.dumps(answer)),
            ):
                with self.assertRaises(ValueError):
                    self.backend.choose(restored_state(), 2, 2)
