"""Synthetic recorded-response binding tests; no real model or native execution."""

import copy
import hashlib
import json
import unittest

import test_history_gameplay as subject
from test_history_choice import CONTEXT, REQUESTS
from chaos.history_choice import RandomHistoryBackend


def synthetic_record():
    probe = RandomHistoryBackend(0)
    _, prompt = probe._prepare(CONTEXT, REQUESTS)
    digest = hashlib.sha256((probe.instructions + "\0" + prompt).encode()).hexdigest()
    return dict(
        status="selected",
        context=copy.deepcopy(CONTEXT),
        candidates=copy.deepcopy(REQUESTS),
        selected=copy.deepcopy(REQUESTS[0]),
        raw_response=json.dumps(REQUESTS[0]),
        prompt_sha256=digest,
        receipt=dict(
            model="gpt-5.6-luna",
            provider="openai-codex",
            record_index=0,
            record=dict(status="completed", prompt_sha256=digest, usage=None),
        ),
    )


class RecordedChoiceTests(unittest.TestCase):
    def test_exact_recorded_choice_once_without_transport(self):
        record = synthetic_record()
        backend = subject.RecordedHistoryBackend(record)
        selected = backend.choose(CONTEXT, REQUESTS)
        self.assertEqual(selected, REQUESTS[0])
        self.assertEqual(backend.attempts, 1)
        self.assertIsNone(backend.choose(CONTEXT, REQUESTS))
        self.assertEqual(backend.last_receipt, record["receipt"])

    def test_context_menu_and_response_binding(self):
        for field, value in (
            ("status", "abstained"),
            ("selected", REQUESTS[1]),
            ("raw_response", json.dumps(REQUESTS[1])),
            ("prompt_sha256", "0" * 64),
            ("context", {}),
            ("candidates", [REQUESTS[0]]),
        ):
            with self.subTest(field=field):
                record = synthetic_record()
                record[field] = value
                with self.assertRaises(ValueError):
                    subject.RecordedHistoryBackend(record).choose(CONTEXT, REQUESTS)

    def test_failed_or_wrong_route_receipt_rejected(self):
        for section, field, value in (
            ("receipt", "model", "other"),
            ("receipt", "provider", "other"),
            ("record", "status", "failed"),
            ("record", "prompt_sha256", "0" * 64),
        ):
            with self.subTest(section=section, field=field):
                record = synthetic_record()
                target = (
                    record["receipt"]
                    if section == "receipt"
                    else record["receipt"]["record"]
                )
                target[field] = value
                with self.assertRaises(ValueError):
                    subject.RecordedHistoryBackend(record).choose(CONTEXT, REQUESTS)
