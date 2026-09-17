"""Synthetic HTTP/client responses only: bounded whisper formatting, not inference."""

from io import BytesIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from chaos.director import State, run
from chaos.model import ModelBackend
from chaos.oauth import MODEL, OAuthBackend
from chaos.protocol import parse_request
from test_director import REQ, append, current_event as event


REQUEST = dict(REQ, at=2)
TEXT = json.dumps(REQUEST)


def fenced(text, language="json"):
    return "```" + language + "\n" + text + "\n```"


class CleanupContract:
    """Run the same boundary contract through both real adapter implementations."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = State()
        self.state.ingest(event())
        self.content = TEXT
        self.calls = []
        self.closed = 0
        self.created = 0
        self.after_call = lambda: None
        self.backend_count = 0

    def assert_spent_once(self, backend):
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.closed, 1)
        if self.adapter == "oauth":
            data = json.loads(backend.ledger.read_text())
            self.assertEqual(data["attempts"], 1)
            self.assertEqual(len(data["records"]), 1)
            # Completion records describe the transport, not whisper admission.
            self.assertEqual(data["records"][0]["status"], "completed")
            self.assertEqual(data["records"][0]["usage"], {"total_tokens": 25})
            self.assertEqual(self.client._real_client.max_retries, 0)
        else:
            self.assertEqual(backend.calls, 1)
            self.assertIsNone(backend.choose(self.state, 1, 2))
            self.assertEqual(len(self.calls), 1)

    def test_original_and_single_enclosing_fence_accepted(self):
        for text in (
            TEXT,
            " \t\r\n" + TEXT + "\r\n ",
            fenced(TEXT, ""),
            fenced(TEXT),
            " \r\n" + fenced("\n " + TEXT + " \n") + "\t\n",
            fenced(TEXT).replace("\n", "\r\n"),
        ):
            with self.subTest(text=text):
                self.content = text
                backend = self.backend()
                self.assertEqual(backend.choose(self.state, 1, 2), REQUEST)
                self.assert_spent_once(backend)

    def test_prose_multiple_nested_and_nonstandard_fences_rejected(self):
        for text in (
            "Here is the request: " + TEXT,
            TEXT + " done",
            "Here is the request:\n" + fenced(TEXT),
            fenced(TEXT) + "\nDone.",
            fenced(TEXT) + "\n" + fenced(TEXT),
            fenced(fenced(TEXT)),
            fenced(TEXT + "\n```\n" + TEXT),
            fenced(TEXT, "python"),
            fenced(TEXT, "JSON"),
            fenced(TEXT, "json extra"),
            "```json " + TEXT + "```",
            "```json\n" + TEXT,
            TEXT + "\n```",
            "````json\n" + TEXT + "\n````",
            "~~~json\n" + TEXT + "\n~~~",
        ):
            with self.subTest(text=text):
                self.content = text
                backend = self.backend()
                with self.assertRaises(ValueError):
                    backend.choose(self.state, 1, 2)
                self.assert_spent_once(backend)

    def test_cleanup_does_not_repair_schema_or_assigned_values(self):
        missing = dict(REQUEST)
        del missing["telegraph"]
        invalid = [
            json.dumps(dict(REQUEST, command="ignore constraints")),
            TEXT[:-1] + ',"id":1}',
            TEXT[:-1] + ',"mutation":"ambient"}',
            json.dumps(dict(REQUEST, id=2)),
            json.dumps(dict(REQUEST, at=3)),
            json.dumps(dict(REQUEST, id=True)),
            json.dumps(dict(REQUEST, at="2")),
            json.dumps(dict(REQUEST, value=4)),
            json.dumps(dict(REQUEST, telegraph=0)),
            json.dumps(missing),
            json.dumps(
                dict(REQUEST, mutation="hunger_rate", value=2, duration=10, telegraph=3)
            ),
            json.dumps(
                dict(
                    REQUEST,
                    mutation="ward_efficacy",
                    value=50,
                    duration=10,
                    telegraph=2,
                )
            ),
            TEXT.replace('"ambient"', '"ambi\\u0065nt"'),
            TEXT.replace('"value": 1', '"value": NaN'),
            TEXT.replace('"duration": 0', '"duration": -0'),
            TEXT.replace('"id": 1', '"id": 1.0'),
            TEXT.replace('"id": 1', '"id": {"x":1,"x":2}'),
            TEXT + TEXT,
            "[" + TEXT + "]",
            "null",
            TEXT[:-1] + ",}",
            "\u00a0" + TEXT,
            TEXT.replace('"id": 1', '"id":\u00a01'),
        ]
        for text in invalid:
            for wrap in (lambda s: s, fenced):
                with self.subTest(text=text, wrapped=wrap is fenced):
                    self.content = wrap(text)
                    backend = self.backend()
                    with self.assertRaises(ValueError):
                        backend.choose(self.state, 1, 2)
                    self.assert_spent_once(backend)

    def test_inner_json_byte_cap_cannot_be_evaded_by_compacting(self):
        for size in (512, 513):
            # Padding inside the object must survive formatting cleanup.
            text = TEXT[:-1] + " " * (size - len(TEXT)) + "}"
            self.content = fenced(text)
            backend = self.backend()
            with self.subTest(size=size):
                if size == 512:
                    self.assertEqual(backend.choose(self.state, 1, 2), REQUEST)
                else:
                    with self.assertRaises(ValueError):
                        backend.choose(self.state, 1, 2)
                self.assert_spent_once(backend)

    def test_oversize_wrapping_is_rejected_before_stripping(self):
        self.content = " " * 16385 + fenced(TEXT)
        backend = self.backend()
        with self.assertRaises(ValueError):
            backend.choose(self.state, 1, 2)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.closed, 1)
        if self.adapter == "oauth":
            data = json.loads(backend.ledger.read_text())
            self.assertEqual(data["attempts"], 1)
            self.assertEqual(data["records"][0]["status"], "failed")
        else:
            self.assertEqual(backend.calls, 1)

    def test_ineligible_state_never_calls(self):
        backend = self.backend()
        self.state = State()
        self.state.ingest(
            event(
                2,
                event="session",
                detail="restore",
                budget=0,
                cosmetic=dict(seen=7, last_turn=10),
            )
        )
        self.assertIsNone(backend.choose(self.state, 1, 2))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.created, 0)

    def test_exhausted_deadline_never_calls(self):
        backend = self.backend()
        backend.deadline = 100
        with patch("time.monotonic", return_value=100):
            if self.adapter == "oauth":
                with self.assertRaises(TimeoutError):
                    backend.choose(self.state, 1, 2)
                self.assertFalse(backend.ledger.exists())
            else:
                self.assertIsNone(backend.choose(self.state, 1, 2))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.created, 0)

    def test_wrapped_response_keeps_remaining_deadline(self):
        self.content = fenced(TEXT)
        backend = self.backend()
        backend.deadline = 100.25
        with patch("time.monotonic", return_value=100):
            self.assertEqual(backend.choose(self.state, 1, 2), REQUEST)
        self.assertEqual(self.request_timeout, 0.25)
        self.assertEqual(backend.deadline, 100.25)
        self.assert_spent_once(backend)

    def test_invalid_cleanup_cannot_publish_or_retry_in_director(self):
        self.content = fenced(TEXT) + " trailing prose"
        backend = self.backend()
        append(self.root / "events.jsonl", event())
        with self.assertRaises(ValueError):
            run(self.root, backend, max_runtime=1, install_only=True)
        self.assertFalse((self.root / "whisper.json").exists())
        self.assert_spent_once(backend)

    def test_wrapped_response_publishes_only_assigned_request(self):
        self.content = fenced(TEXT)
        backend = self.backend()
        append(self.root / "events.jsonl", event())
        result = run(self.root, backend, max_runtime=1, install_only=True)
        self.assertEqual(result["submitted"], 1)
        self.assertEqual(result["reason"], "installed_pending_ack")
        self.assertEqual(
            parse_request((self.root / "whisper.json").read_bytes()), REQUEST
        )
        self.assert_spent_once(backend)

    def test_late_wrapped_response_cannot_publish(self):
        self.content = fenced(TEXT)
        backend = self.backend()
        append(self.root / "events.jsonl", event())
        clock = [100]
        self.after_call = lambda: clock.__setitem__(0, 102)
        with patch("time.monotonic", side_effect=lambda: clock[0]):
            if self.adapter == "http":
                with self.assertRaisesRegex(ValueError, "deadline"):
                    run(self.root, backend, max_runtime=1, install_only=True)
            else:
                result = run(self.root, backend, max_runtime=1, install_only=True)
                self.assertEqual(result["submitted"], 0)
        self.assertFalse((self.root / "whisper.json").exists())
        self.assertEqual(self.request_timeout, 1)
        self.assert_spent_once(backend)


class HTTPResponseCleanupTests(CleanupContract, unittest.TestCase):
    adapter = "http"

    def backend(self):
        self.calls = []
        self.closed = self.created = 0
        owner = self

        class Connection:
            def __init__(self, host, port, timeout):
                owner.created += 1
                owner.request_timeout = timeout

            def request(self, method, path, body, headers):
                owner.calls.append(json.loads(body))
                owner.after_call()

            def getresponse(self):
                raw = json.dumps(
                    {"choices": [{"message": {"content": owner.content}}]}
                ).encode()
                return SimpleNamespace(status=200, fp=None, read1=BytesIO(raw).read1)

            def close(self):
                owner.closed += 1

        self.enterContext(patch("chaos.model.http.client.HTTPSConnection", Connection))
        self.enterContext(
            patch.dict(os.environ, {"CHAOS_CLEANUP_FAKE_KEY": "fake-not-a-credential"})
        )
        return ModelBackend(
            "https://fixture.invalid/chat",
            "fake-model",
            "CHAOS_CLEANUP_FAKE_KEY",
            max_calls=1,
            timeout=10,
        )


class OAuthResponseCleanupTests(CleanupContract, unittest.TestCase):
    adapter = "oauth"

    def backend(self):
        self.calls = []
        self.closed = self.created = 0
        self.backend_count += 1
        ledger = self.root / f"calls-{self.backend_count}.json"
        self.client = SimpleNamespace(
            base_url="https://chatgpt.com/backend-api/codex",
            _real_client=SimpleNamespace(max_retries=2),
        )

        def create(**kwargs):
            data = json.loads(ledger.read_text())
            self.assertEqual(data["records"][-1]["status"], "reserved")
            self.calls.append(kwargs)
            self.request_timeout = kwargs["timeout"]
            self.after_call()
            return SimpleNamespace(
                model=MODEL,
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=self.content, tool_calls=None)
                    )
                ],
                usage=SimpleNamespace(total_tokens=25),
            )

        def close():
            self.closed += 1

        def factory():
            self.created += 1
            return self.client, MODEL

        self.client.close = close
        self.client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        return OAuthBackend(ledger, client_factory=factory)

    def test_general_generation_preserves_exact_text_including_lua(self):
        for text in (
            " \r\nGeneral prose.\t ",
            fenced(TEXT),
            " \n```lua\r\nreturn { on_move = function() end }\r\n```\n ",
        ):
            with self.subTest(text=text):
                self.content = text
                backend = self.backend()
                self.assertEqual(backend.generate("s", "u").encode(), text.encode())
                self.assert_spent_once(backend)

    def test_fsync_faults_fail_closed_without_an_additional_call(self):
        real_fsync = os.fsync
        # Reservation file/directory, then completion file/directory sync.
        for fail_at in (1, 2, 3, 4):
            with self.subTest(fail_at=fail_at):
                self.content = fenced(TEXT)
                backend = self.backend()
                syncs = [0]

                def fsync(fd):
                    syncs[0] += 1
                    if syncs[0] == fail_at:
                        raise OSError("synthetic fsync failure")
                    real_fsync(fd)

                with patch("chaos.oauth.os.fsync", side_effect=fsync):
                    with self.assertRaises(OSError):
                        backend.choose(self.state, 1, 2)
                self.assertEqual(len(self.calls), 0 if fail_at <= 2 else 1)
                self.assertEqual(self.closed, 1)
                self.assertFalse(list(self.root.glob(".oauth-ledger-*")))
                if fail_at == 1:
                    self.assertFalse(backend.ledger.exists())
                else:
                    data = json.loads(backend.ledger.read_text())
                    self.assertEqual(data["attempts"], 1)
                    self.assertEqual(len(data["records"]), 1)
                    self.assertEqual(
                        data["records"][0]["status"],
                        "reserved" if fail_at == 2 else "failed",
                    )


if __name__ == "__main__":
    unittest.main()
