"""No real provider in unit tests; exercise pinned route and durable call limit."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("chaos.oauth"), "OAuth backend not implemented"
        )
        from chaos.oauth import OAuthBackend

        self.Backend = OAuthBackend
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Path(self.tmp.name) / "calls.json"
        self.calls = []
        self.client = SimpleNamespace(
            base_url="https://chatgpt.com/backend-api/codex",
            _real_client=SimpleNamespace(max_retries=2),
        )
        self.client.close = lambda: None

        def create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                model="gpt-5.6-luna",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content='{"ok":true}', tool_calls=None)
                    )
                ],
                usage=SimpleNamespace(
                    input_tokens=20, output_tokens=5, total_tokens=25
                ),
            )

        self.client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        self.factory = lambda: (self.client, "gpt-5.6-luna")

    def test_pinned_route_no_tools_and_persistent_cap(self):
        for _ in range(20):
            b = self.Backend(self.ledger, client_factory=self.factory)
            self.assertEqual(
                b.generate("Only JSON", 'Return {"ok":true}'), '{"ok":true}'
            )
        self.assertEqual(len(self.calls), 20)
        with self.assertRaises(ValueError):
            self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        self.assertEqual(len(self.calls), 20)
        self.assertEqual(self.client._real_client.max_retries, 0)
        self.assertTrue(
            all(c["model"] == "gpt-5.6-luna" and not c.get("tools") for c in self.calls)
        )
        data = json.loads(self.ledger.read_text())
        self.assertEqual(data["attempts"], 20)
        self.assertEqual(data["records"][-1]["usage"]["total_tokens"], 25)

    def test_failure_consumes_reservation_and_routes_fail_closed(self):
        def fail(**kw):
            raise TimeoutError("do not leak raw provider error")

        self.client.chat.completions.create = fail
        with self.assertRaises(TimeoutError):
            self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        self.assertEqual(json.loads(self.ledger.read_text())["attempts"], 1)
        self.client.base_url = "https://api.openai.com/v1"
        with self.assertRaises(ValueError):
            self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        with self.assertRaises(ValueError):
            self.Backend(
                self.ledger, client_factory=lambda: (self.client, "other-model")
            ).generate("s", "u")
        self.assertEqual(json.loads(self.ledger.read_text())["attempts"], 1)

    def test_directory_sync_precedes_inference(self):
        import os
        import stat
        from unittest.mock import patch

        synced = []
        real_fsync = os.fsync
        real_create = self.client.chat.completions.create

        def sync(fd):
            real_fsync(fd)
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                synced.append(True)

        def create(**kwargs):
            self.assertTrue(
                synced, "reservation directory was not synced before inference"
            )
            return real_create(**kwargs)

        self.client.chat.completions.create = create
        with patch("chaos.oauth.os.fsync", side_effect=sync):
            self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        self.assertEqual(len(self.calls), 1)

    def test_bounds_and_no_secret_copy(self):
        b = self.Backend(self.ledger, client_factory=self.factory)
        with self.assertRaises(ValueError):
            b.generate("x" * 8193, "u")
        self.assertFalse(self.ledger.exists())
        b.generate("s", "u")
        data = json.loads(self.ledger.read_text())
        self.assertNotIn("api_key", str(data))
        self.assertEqual(
            data["billing"], "subscription OAuth; cash charge not reported"
        )
        self.assertFalse(data["paid_api_fallback"])
