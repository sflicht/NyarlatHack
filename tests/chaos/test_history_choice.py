"""Synthetic transport tests; no model calls or native gameplay evidence."""

import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from chaos.history_choice import OAuthHistoryBackend, RandomHistoryBackend


CONTEXT = {
    "history_context_v": 1,
    "summary": {"observed": {"turn": 20}, "recent": []},
    "episodes": {"episodes": []},
    "prior_whispers": [],
    "prior_coverage": {"shown": 0, "omitted": 0},
    "next_use": {"families": [], "menu": []},
}
REQUESTS = [
    dict(v=1, id=1, at=2, mutation="hunger_rate", value=2, duration=n, telegraph=3)
    for n in (10, 20)
]


class FakeTransport:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.deadline = float("inf")
        self.receipt = {"synthetic_transport": True}

    def generate(self, instructions, prompt, *, return_receipt=False):
        self.calls.append((instructions, prompt, return_receipt))
        if self.error is not None:
            raise self.error
        return self.response, self.receipt


class HistoryChoiceTests(unittest.TestCase):
    def oauth(self, response):
        transport = FakeTransport(response)
        return OAuthHistoryBackend(transport), transport

    def test_seeded_choices_reproduce_and_span_both_durations(self):
        durations = set()
        for seed in (0, 1, 7):
            first = RandomHistoryBackend(seed).choose(CONTEXT, REQUESTS)
            self.assertEqual(
                first, RandomHistoryBackend(seed).choose(CONTEXT, REQUESTS)
            )
            self.assertIn(first, REQUESTS)
            durations.add(first["duration"])
        self.assertEqual(durations, {10, 20})

    def test_empty_domain_is_quiet_without_a_transport_call(self):
        backend, transport = self.oauth("not a response")
        self.assertIsNone(backend.choose(CONTEXT, []))
        self.assertEqual(transport.calls, [])
        self.assertEqual(backend.attempts, 0)
        random = RandomHistoryBackend(0)
        self.assertIsNone(random.choose(CONTEXT, []))
        self.assertEqual(random.attempts, 0)

    def test_exact_response_and_receipt_are_independent_copies(self):
        backend, transport = self.oauth(json.dumps(REQUESTS[1]))
        request = backend.choose(CONTEXT, REQUESTS)
        self.assertEqual(request, REQUESTS[1])
        request["duration"] = 1
        transport.receipt["synthetic_transport"] = False
        self.assertEqual(REQUESTS[1]["duration"], 20)
        self.assertTrue(backend.last_receipt["synthetic_transport"])
        instructions, prompt, receipt = transport.calls[0]
        self.assertTrue(receipt)
        self.assertIn("admission", instructions)
        self.assertEqual(
            json.loads(prompt), {"context": CONTEXT, "allowed_requests": REQUESTS}
        )
        self.assertEqual(backend.last_response, json.dumps(REQUESTS[1]))

    def test_single_fence_is_formatting_only(self):
        backend, _ = self.oauth("```json\n" + json.dumps(REQUESTS[0]) + "\n```")
        self.assertEqual(backend.choose(CONTEXT, REQUESTS), REQUESTS[0])

    def test_only_exact_abstention_is_quiet(self):
        backend, transport = self.oauth('{"abstain":true}')
        self.assertIsNone(backend.choose(CONTEXT, REQUESTS))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(backend.attempts, 1)
        for value in (
            '{"abstain":1}',
            '{"abstain":false}',
            '{"abstain":true,"why":"x"}',
            "null",
        ):
            with self.subTest(value=value):
                bad, _ = self.oauth(value)
                with self.assertRaises(ValueError):
                    bad.choose(CONTEXT, REQUESTS)

    def test_registry_valid_but_outside_menu_is_rejected(self):
        changes = (
            {"duration": 11},
            {"id": 2},
            {"at": 3},
            {"mutation": "ward_efficacy", "value": 50, "telegraph": 2},
        )
        for change in changes:
            with self.subTest(change=change):
                backend, transport = self.oauth(json.dumps(dict(REQUESTS[0], **change)))
                with self.assertRaises(ValueError):
                    backend.choose(CONTEXT, REQUESTS)
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(backend.attempts, 1)

    def test_failed_transport_spends_attempt_without_retry(self):
        error = RuntimeError("synthetic transport failure")
        transport = FakeTransport("", error)
        backend = OAuthHistoryBackend(transport)
        with self.assertRaises(RuntimeError) as caught:
            backend.choose(CONTEXT, REQUESTS)
        self.assertIs(caught.exception, error)
        self.assertIsNone(backend.choose(CONTEXT, REQUESTS))
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(backend.attempts, 1)

    def test_invalid_response_has_no_retry_or_substitution(self):
        for response in (
            '{"v":1,"v":1}',
            "choose " + json.dumps(REQUESTS[0]),
            "x" * 8193,
        ):
            with self.subTest(response=response[:40]):
                backend, transport = self.oauth(response)
                with self.assertRaises(ValueError):
                    backend.choose(CONTEXT, REQUESTS)
                self.assertIsNone(backend.choose(CONTEXT, REQUESTS))
                self.assertEqual(len(transport.calls), 1)

    def test_attempt_bounds_and_default_single_choice(self):
        for cls, arg in (
            (RandomHistoryBackend, 0),
            (OAuthHistoryBackend, FakeTransport("")),
        ):
            for cap in (True, 0, 3, 1.0):
                with self.subTest(cls=cls.__name__, cap=cap):
                    with self.assertRaises(ValueError):
                        cls(arg, max_attempts=cap)
        backend = RandomHistoryBackend(0)
        self.assertIn(backend.choose(CONTEXT, REQUESTS), REQUESTS)
        self.assertIsNone(backend.choose(CONTEXT, REQUESTS))
        self.assertEqual(backend.attempts, 1)

    def test_invalid_seed_rejected(self):
        for seed in (True, 1.0, "0", None):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    RandomHistoryBackend(seed)

    def test_prompt_byte_cap_precedes_transport(self):
        context = copy.deepcopy(CONTEXT)
        context["episodes"]["padding"] = "x" * 8192
        backend, transport = self.oauth(json.dumps(REQUESTS[0]))
        with self.assertRaises(ValueError):
            backend.choose(context, REQUESTS)
        self.assertEqual(transport.calls, [])
        self.assertEqual(backend.attempts, 0)

    def test_context_boundary_rejects_host_proof_and_nonfinite_values(self):
        bad_contexts = [
            dict(CONTEXT, checkpoint={"host_path": "/private"}),
            dict(CONTEXT, history_context_v=True),
        ]
        nonfinite = copy.deepcopy(CONTEXT)
        nonfinite["summary"]["observed"]["turn"] = float("nan")
        bad_contexts.append(nonfinite)
        for context in bad_contexts:
            with self.subTest(context=context):
                backend, transport = self.oauth(json.dumps(REQUESTS[0]))
                with self.assertRaises(ValueError):
                    backend.choose(context, REQUESTS)
                self.assertEqual(transport.calls, [])

    def test_bad_menus_rejected_before_transport(self):
        menus = [
            [REQUESTS[0], REQUESTS[0]],
            REQUESTS * 2,
            [dict(REQUESTS[0], value=True)],
        ]
        for menu in menus:
            with self.subTest(menu=menu):
                backend, transport = self.oauth(json.dumps(REQUESTS[0]))
                with self.assertRaises(ValueError):
                    backend.choose(CONTEXT, menu)
                self.assertEqual(transport.calls, [])

    def test_deadline_prevents_call_and_is_forwarded(self):
        backend, transport = self.oauth(json.dumps(REQUESTS[0]))
        backend.deadline = 0
        with self.assertRaises(TimeoutError):
            backend.choose(CONTEXT, REQUESTS)
        self.assertEqual(transport.calls, [])
        live, transport = self.oauth(json.dumps(REQUESTS[0]))
        live.deadline = 10**12
        live.choose(CONTEXT, REQUESTS)
        self.assertEqual(transport.deadline, 10**12)


if __name__ == "__main__":
    unittest.main()
