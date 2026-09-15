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

    def test_scoped_reservation_precedes_factory_and_persists_limit(self):
        from chaos.oauth import MODEL

        made = []

        def factory():
            made.append(True)
            data = json.loads(self.ledger.read_text())
            self.assertEqual(data["records"][-1]["status"], "reserved")
            self.assertEqual(data["records"][-1]["purpose"], "curio-generation")
            return self.client, MODEL

        for _ in range(2):
            backend = self.Backend(
                self.ledger,
                purpose="curio-generation",
                fresh_ledger=True,
                client_factory=factory,
            )
            text, receipt = backend.generate("s", "u", return_receipt=True)
            self.assertEqual(text, '{"ok":true}')
            self.assertEqual(receipt["record_index"], len(made) - 1)
        with self.assertRaises(ValueError):
            self.Backend(
                self.ledger, purpose="curio-generation", client_factory=factory
            ).generate("s", "u")
        self.assertEqual(len(made), 2)

    def test_scoped_last_overall_slot_includes_legacy_records(self):
        for _ in range(19):
            self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        self.Backend(
            self.ledger, purpose="curio-generation", client_factory=self.factory
        ).generate("s", "u")
        with self.assertRaises(ValueError):
            self.Backend(
                self.ledger,
                purpose="curio-generation",
                client_factory=lambda: self.fail("factory on exhausted ledger"),
            ).generate("s", "u")
        self.assertEqual(json.loads(self.ledger.read_text())["attempts"], 20)

    def test_scoped_bad_metadata_and_ledger_fail_before_factory(self):
        from unittest.mock import Mock

        factory = Mock(side_effect=AssertionError("no credentials"))
        for purpose in ("other", {}, True):
            with self.assertRaises(ValueError):
                self.Backend(self.ledger, purpose=purpose, client_factory=factory)
        with self.assertRaises(FileNotFoundError):
            self.Backend(
                self.ledger, purpose="curio-generation", client_factory=factory
            ).generate("s", "u")
        self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        good = json.loads(self.ledger.read_text())
        import copy

        bad = [b"[]", b'{"model":1,"model":2}', b"{}", b"x" * 32769]
        for key, value in (
            ("limit", 20.0),
            ("cash_ceiling_usd", True),
            ("attempts", True),
            ("records", {}),
            ("billing", "API"),
        ):
            data = copy.deepcopy(good)
            data[key] = value
            bad.append(json.dumps(data).encode())
        for key, value in (
            ("purpose", "other"),
            ("purpose", None),
            ("metadata", {}),
            ("status", "accepted"),
            ("usage", {"total_tokens": True}),
            ("prompt_sha256", "bad"),
        ):
            data = copy.deepcopy(good)
            data["records"][0][key] = value
            bad.append(json.dumps(data).encode())
        for raw in bad:
            self.ledger.write_bytes(raw)
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError):
                self.Backend(
                    self.ledger, purpose="curio-generation", client_factory=factory
                ).generate("s", "u")
        factory.assert_not_called()

    def test_scoped_concurrent_last_slot_atomic_nonblocking(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        barrier = Barrier(2)
        self.Backend(
            self.ledger,
            purpose="curio-generation",
            fresh_ledger=True,
            client_factory=self.factory,
        ).generate("s", "u")

        def attempt(_):
            barrier.wait(timeout=5)
            try:
                self.Backend(
                    self.ledger, purpose="curio-generation", client_factory=self.factory
                ).generate("s", "u")
                return True
            except (ValueError, BlockingIOError):
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(attempt, range(2)))
        self.assertEqual(sum(result), 1)
        self.assertEqual(json.loads(self.ledger.read_text())["attempts"], 2)
        self.assertEqual(len(self.calls), 2)

    def test_receipt_update_sync_failure_is_not_retried(self):
        from unittest.mock import patch
        import os

        backend = self.Backend(
            self.ledger,
            purpose="curio-generation",
            fresh_ledger=True,
            client_factory=self.factory,
        )
        original = backend._ledger_update
        updates = []

        def update(fn, **kw):
            if kw.get("write", True):
                updates.append(True)
                if len(updates) == 2:
                    # Complete replacement bytes may survive a directory-sync error.
                    sync = os.fsync

                    def fail_directory(fd):
                        import stat

                        if stat.S_ISDIR(os.fstat(fd).st_mode):
                            raise OSError("synthetic uncertain completed publication")
                        sync(fd)

                    with patch("os.fsync", side_effect=fail_directory):
                        return original(fn, **kw)
            return original(fn, **kw)

        with patch.object(backend, "_ledger_update", update):
            with self.assertRaises(OSError):
                backend.generate("s", "u")
        self.assertEqual(
            len(updates),
            2,
            "must not attempt failure rewrite after uncertain ledger write",
        )
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(
            json.loads(self.ledger.read_text())["records"][0]["status"], "completed"
        )
        self.assertEqual(backend.last_receipt["record"]["status"], "reserved")

    def test_preflight_is_read_only_and_requires_retained_lock(self):
        from unittest.mock import patch

        backend = self.Backend(
            self.ledger,
            purpose="curio-generation",
            fresh_ledger=True,
            client_factory=self.factory,
        )
        with patch("os.fsync", side_effect=AssertionError("preflight writes")):
            backend.preflight()
        self.assertEqual(list(self.ledger.parent.iterdir()), [])
        backend.generate("s", "u")
        before = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.ledger.parent.iterdir()
        }
        with patch("os.fsync", side_effect=AssertionError("preflight writes")):
            backend.preflight()
            backend.receipt(0)
        self.assertEqual(
            before,
            {
                p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.ledger.parent.iterdir()
            },
        )
        Path(str(self.ledger) + ".lock").unlink()
        with self.assertRaises((ValueError, OSError)):
            backend.preflight()
        self.assertFalse(Path(str(self.ledger) + ".lock").exists())

    def test_response_container_shapes_fail_closed(self):
        from types import SimpleNamespace as NS

        responses = [
            NS(model="gpt-5.6-luna", choices=None),
            NS(model="gpt-5.6-luna", choices={"wrong": 1}),
            NS(model="gpt-5.6-luna", choices=[None]),
            NS(
                model="gpt-5.6-luna",
                choices=[
                    NS(
                        message=NS(
                            content="{}", tool_calls=None, function_call="forbidden"
                        )
                    )
                ],
            ),
        ]
        for index, response in enumerate(responses):
            ledger = self.ledger.parent / f"shape-{index}.json"
            self.client.chat.completions.create = lambda **kw: response
            with self.assertRaises(ValueError):
                self.Backend(
                    ledger,
                    purpose="curio-generation",
                    fresh_ledger=True,
                    client_factory=self.factory,
                ).generate("s", "u")
            self.assertEqual(
                json.loads(ledger.read_text())["records"][0]["status"], "failed"
            )

    def test_private_ledger_and_partial_temporary_fail_closed(self):
        import os
        from unittest.mock import Mock

        self.Backend(self.ledger, client_factory=self.factory).generate("s", "u")
        factory = Mock(side_effect=AssertionError("no credential factory"))
        backend = self.Backend(
            self.ledger, purpose="curio-generation", client_factory=factory
        )
        self.ledger.chmod(0o644)
        with self.assertRaises(ValueError):
            backend.preflight()
        self.ledger.chmod(0o600)
        linked = self.ledger.parent / "alias"
        os.link(self.ledger, linked)
        with self.assertRaises(ValueError):
            backend.preflight()
        linked.unlink()
        partial = self.ledger.parent / ".oauth-ledger-uncertain"
        partial.write_bytes(b"partial")
        partial.chmod(0o600)
        with self.assertRaises(ValueError):
            backend.preflight()
        partial.unlink()
        self.ledger.rename(linked)
        self.ledger.symlink_to(linked)
        with self.assertRaises((OSError, ValueError)):
            backend.preflight()
        factory.assert_not_called()

    def test_all_ledger_sync_boundaries_follow_purpose_failure_policy(self):
        import os
        from unittest.mock import Mock, patch

        for purpose in (None, "curio-generation"):
            for fail_at in (1, 2, 3, 4):
                with self.subTest(purpose=purpose, fail_at=fail_at):
                    with tempfile.TemporaryDirectory(dir=self.ledger.parent) as root:
                        ledger = Path(root) / "authorization.json"
                        factory = Mock(side_effect=self.factory)
                        close = Mock()
                        self.client.close = close
                        backend = self.Backend(
                            ledger,
                            purpose=purpose,
                            fresh_ledger=True,
                            client_factory=factory,
                        )
                        real_sync = os.fsync
                        syncs = []
                        self.calls.clear()

                        def fsync(fd):
                            syncs.append(fd)
                            if len(syncs) == fail_at:
                                raise OSError("synthetic exact sync boundary")
                            real_sync(fd)

                        with patch("os.fsync", side_effect=fsync):
                            with self.assertRaises(OSError):
                                backend.generate("s", "u")
                        legacy_completion = purpose is None and fail_at > 2
                        # Legacy completion failure writes failed (file + directory);
                        # scoped uncertainty forbids any recovery status write.
                        self.assertEqual(len(syncs), fail_at + 2 * legacy_completion)
                        self.assertEqual(len(self.calls), int(fail_at > 2))
                        made = int(purpose is None or fail_at > 2)
                        self.assertEqual(factory.call_count, made)
                        self.assertEqual(close.call_count, made)
                        self.assertEqual(
                            bool(list(Path(root).glob(".oauth-ledger-*"))),
                            purpose is not None and fail_at in (1, 3),
                        )
                        if fail_at == 1:
                            self.assertFalse(ledger.exists())
                        else:
                            data = json.loads(ledger.read_bytes())
                            self.assertEqual(data["attempts"], 1)
                            expected = (
                                "failed"
                                if legacy_completion
                                else "completed"
                                if fail_at == 4
                                else "reserved"
                            )
                            self.assertEqual(data["records"][0]["status"], expected)
                            if legacy_completion:
                                self.assertEqual(
                                    data["records"][0]["error_type"], "OSError"
                                )
                        if fail_at <= 2:
                            self.assertIsNone(backend.last_receipt)
                        else:
                            self.assertEqual(
                                backend.last_receipt["record"]["status"],
                                "failed" if legacy_completion else "reserved",
                            )

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
