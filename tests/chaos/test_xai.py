"""xAI transports and ledger, offline with fake transports.

No test contacts a provider or imports Hermes. A test that needs "a key is
set" builds a throwaway value in this process and writes it nowhere.
"""

import builtins
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch
import uuid

from chaos import xai
from chaos.author_config import resolve

MODEL = "grok-test-model"  # fixture id; real runs pass --author-model


def throwaway():
    """A per-test value, generated at run time, never written to disk."""
    return "t" + uuid.uuid4().hex + uuid.uuid4().hex


class FakeClient:
    def __init__(self, model=MODEL, content='{"ok":true}', base_url=xai.XAI_BASE_URL):
        self.base_url = base_url
        self.calls = []
        self.closed = 0
        self._real_client = NS(max_retries=2)
        self.model = model
        self.content = content
        self.error = None
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return NS(
            model=self.model,
            choices=[NS(message=NS(content=self.content, tool_calls=None))],
            usage=NS(input_tokens=11, output_tokens=7, total_tokens=18),
        )

    def close(self):
        self.closed += 1


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = xai.XaiLedger(self.root / "ledger" / "xai-ledger.jsonl")
        self.config = resolve("xai-oauth", MODEL)
        self.client = FakeClient()
        self.factories = 0

    def factory(self):
        self.factories += 1
        # The reservation is durable before any credential is resolved.
        rows = self.ledger.rows()
        self.assertEqual(rows[-1]["status"], "reserved")
        return self.client, MODEL

    def backend(self, **kwargs):
        kwargs.setdefault("run_id", "run-1")
        kwargs.setdefault("surface", "curio")
        kwargs.setdefault("client_factory", self.factory)
        return xai.build(self.config, self.ledger, **kwargs)


class LedgerTests(Base):
    def test_completed_call_rows_and_receipt(self):
        content, receipt = self.backend().generate("sys", "user", return_receipt=True)
        self.assertEqual(content, '{"ok":true}')
        rows = self.ledger.rows()
        self.assertEqual([r["status"] for r in rows], ["reserved", "completed"])
        done = rows[-1]
        self.assertEqual(done["attempt"], rows[0]["attempt"])
        self.assertEqual(
            {k: done[k] for k in ("provider", "model", "route", "run_id", "surface")},
            dict(
                provider="xai-oauth",
                model=MODEL,
                route="hermes-xai-oauth",
                run_id="run-1",
                surface="curio",
            ),
        )
        self.assertEqual(done["http_status"], 200)
        self.assertEqual(
            done["usage"], dict(input_tokens=11, output_tokens=7, total_tokens=18)
        )
        self.assertEqual(len(done["prompt_sha256"]), 64)
        self.assertEqual(len(done["response_sha256"]), 64)
        self.assertIsInstance(done["latency_s"], float)
        self.assertEqual(receipt["record"], done)
        self.assertEqual(receipt["provider"], "xai-oauth")
        self.assertEqual(self.client._real_client.max_retries, 0)
        self.assertEqual(self.client.calls[0]["model"], MODEL)
        self.assertEqual(self.client.calls[0]["tools"], [])
        self.assertEqual(self.client.closed, 1)
        self.assertEqual(os.stat(self.ledger.path).st_mode & 0o777, 0o600)

    def test_failure_is_ledgered_and_not_retried(self):
        self.client.error = TimeoutError("slow")
        backend = self.backend()
        with self.assertRaises(TimeoutError):
            backend.generate("sys", "user")
        rows = self.ledger.rows()
        self.assertEqual([r["status"] for r in rows], ["reserved", "failed"])
        self.assertEqual(rows[-1]["error_type"], "TimeoutError")
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(backend.last_receipt["record"]["status"], "failed")

    def test_reservation_survives_a_killed_request(self):
        def killed(**_):
            raise KeyboardInterrupt  # not an Exception: no "failed" row

        self.client.chat.completions.create = killed
        with self.assertRaises(KeyboardInterrupt):
            self.backend().generate("sys", "user")
        self.assertEqual([r["status"] for r in self.ledger.rows()], ["reserved"])

    def test_per_surface_per_game_cap(self):
        for _ in range(xai.SURFACE_GAME_CAP):
            self.backend().generate("s", "u")
        with self.assertRaises(xai.LedgerCapReached):
            self.backend().generate("s", "u")
        with self.assertRaises(xai.LedgerCapReached):
            self.backend().preflight()
        self.assertEqual(self.factories, xai.SURFACE_GAME_CAP)
        # Another surface, and another game, have their own allowance.
        self.backend(surface="hound").generate("s", "u")
        self.backend(run_id="run-2").generate("s", "u")

    def test_daily_and_file_caps(self):
        ledger = xai.XaiLedger(self.root / "small.jsonl", daily_cap=2, file_cap=3)
        build = lambda run: xai.build(  # noqa: E731
            self.config,
            ledger,
            run_id=run,
            surface="curio",
            client_factory=lambda: (self.client, MODEL),
        )
        build("a").generate("s", "u")
        build("b").generate("s", "u")
        with self.assertRaises(xai.LedgerCapReached):
            build("c").generate("s", "u")
        rows = ledger.rows()
        for row in rows:
            row["day"] = "2000-01-01"  # yesterday's requests
        ledger.path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        build("c").generate("s", "u")
        with self.assertRaises(xai.LedgerCapReached):
            build("d").generate("s", "u")  # file cap 3

    def test_default_caps(self):
        self.assertEqual(
            (xai.SURFACE_GAME_CAP, xai.DAILY_CAP, xai.FILE_CAP), (3, 200, 2000)
        )
        ledger = xai.XaiLedger(self.root / "x.jsonl", daily_cap=50)
        self.assertEqual(ledger.daily_cap, 50)
        for bad in (0, -1, 2001, True, 1.5):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    xai.XaiLedger(self.root / "y.jsonl", daily_cap=bad)

    def test_corrupt_or_shared_ledger_fails_closed(self):
        self.backend().generate("s", "u")
        with open(self.ledger.path, "ab") as f:
            f.write(b'{"partial":')
        with self.assertRaises(ValueError):
            self.backend().generate("s", "u")
        self.ledger.path.write_text("")
        os.chmod(self.ledger.path, 0o644)
        with self.assertRaises(ValueError):
            self.backend().generate("s", "u")

    def test_route_and_model_checks(self):
        for client, served in (
            (FakeClient(base_url="https://example.invalid/v1"), MODEL),
            (FakeClient(base_url="http://api.x.ai/v1"), MODEL),
            (FakeClient(), "another-model"),
            (FakeClient(model="another-model"), MODEL),
            (FakeClient(content=None), MODEL),
        ):
            with self.subTest(base=client.base_url, served=served):
                backend = self.backend(
                    run_id="run-" + uuid.uuid4().hex[:8],
                    client_factory=lambda c=client, m=served: (c, m),
                )
                with self.assertRaises(ValueError):
                    backend.generate("s", "u")
                self.assertEqual(self.ledger.rows()[-1]["status"], "failed")

    def test_invalid_labels_and_prompts(self):
        for kwargs in (dict(run_id="../x"), dict(surface=""), dict(run_id="A")):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.backend(**kwargs)
        with self.assertRaises(ValueError):
            self.backend().generate("s", "x" * (xai.MAX_PROMPT_BYTES + 1))
        self.assertFalse(self.ledger.path.exists())


class BuildTests(Base):
    def test_nothing_configured_builds_nothing(self):
        self.assertIsNone(xai.build(None, self.ledger, run_id="r", surface="curio"))
        self.assertFalse(self.ledger.path.exists())

    def test_provider_classes(self):
        self.assertIsInstance(self.backend(), xai.XaiOAuthBackend)
        key = throwaway()
        config = resolve("xai", MODEL)
        backend = xai.build(
            config,
            self.ledger,
            run_id="r",
            surface="curio",
            environ={"XAI_API_KEY": key},
        )
        self.assertIsInstance(backend, xai.XaiApiKeyBackend)
        with self.assertRaises(ValueError):
            xai.build(
                resolve("openai-codex", MODEL), self.ledger, run_id="r", surface="c"
            )
        with self.assertRaises(ValueError):
            xai.XaiApiKeyBackend(self.config, self.ledger, run_id="r", surface="c")

    def test_oauth_without_hermes_is_no_model_reachable(self):
        real_import = builtins.__import__

        def no_hermes(name, *args, **kwargs):
            if name == "agent" or name.startswith("agent."):
                raise ImportError("no Hermes")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=no_hermes):
            with self.assertRaises(xai.NoModelReachable):
                xai.build(self.config, self.ledger, run_id="r", surface="curio")
        # Hermes is imported at build time, so nothing was reserved.
        self.assertFalse(self.ledger.path.exists())

    def test_oauth_without_login_is_ledgered_no_model_reachable(self):
        calls = []

        def builder(model):
            calls.append(model)
            return None, None

        with patch("chaos.xai._hermes_xai_builder", return_value=builder):
            backend = xai.build(self.config, self.ledger, run_id="r", surface="curio")
        self.assertEqual(calls, [])  # no credential resolved at build
        with self.assertRaises(xai.NoModelReachable):
            backend.generate("s", "u")
        self.assertEqual(calls, [MODEL])
        self.assertEqual(
            [r["status"] for r in self.ledger.rows()], ["reserved", "failed"]
        )

    def test_api_key_variable_unset_is_no_model_reachable(self):
        for env, config in (
            ({}, resolve("xai", MODEL)),
            ({"XAI_API_KEY": ""}, resolve("xai", MODEL)),
            ({"XAI_API_KEY": throwaway()}, resolve("xai", MODEL, "OTHER_VAR")),
        ):
            with self.subTest(env=sorted(env), key_env=config.key_env):
                with self.assertRaises(xai.NoModelReachable) as caught:
                    xai.build(config, self.ledger, run_id="r", surface="c", environ=env)
                self.assertEqual(str(caught.exception), f"{config.key_env} is not set")
        self.assertFalse(self.ledger.path.exists())

    def test_override_variable_is_read(self):
        key = throwaway()
        config = resolve("xai", MODEL, "OTHER_VAR")
        backend = xai.build(
            config, self.ledger, run_id="r", surface="c", environ={"OTHER_VAR": key}
        )
        self.assertIsInstance(backend, xai.XaiApiKeyBackend)


class FakeHTTPS:
    """Stands in for http.client.HTTPSConnection; captures the request."""

    seen = []

    def __init__(self, host, port, timeout):
        self.host, self.port = host, port

    def request(self, method, path, body, headers):
        FakeHTTPS.seen.append(
            dict(method=method, path=path, body=body, headers=headers)
        )

    def getresponse(self):
        body = json.dumps(
            dict(
                model=MODEL,
                choices=[dict(message=dict(content='{"ok":true}'))],
                usage=dict(prompt_tokens=3, completion_tokens=2, total_tokens=5),
            )
        ).encode()
        return NS(status=200, read=lambda n: body)

    def close(self):
        pass


class KeyNeverLeaksTests(Base):
    """A set key's value never appears in the ledger, a receipt, run evidence,
    exception text or any repr. Only the outgoing request header carries it."""

    def scan(self, key, *texts):
        for text in texts:
            self.assertNotIn(key, text)

    def test_key_value_absent_everywhere_but_the_request_header(self):
        key = throwaway()
        config = resolve("xai", MODEL)
        run_dir = self.root / "run"
        run_dir.mkdir(mode=0o700)
        FakeHTTPS.seen.clear()
        with (
            patch.dict(os.environ, {"XAI_API_KEY": key}),
            patch("chaos.xai.http.client.HTTPSConnection", FakeHTTPS),
        ):
            backend = xai.build(config, self.ledger, run_id="run-1", surface="curio")
            content, receipt = backend.generate("sys", "user", return_receipt=True)
            # Run evidence as a later slice writes it: the receipt and choice record.
            (run_dir / "receipt.json").write_text(json.dumps(receipt))
            (run_dir / "choice.json").write_text(json.dumps(config.record()))

            # A failing call: its exception text and ledger row.
            def boom(*a, **k):
                raise RuntimeError("upstream failure")

            with patch.object(FakeHTTPS, "getresponse", boom):
                with self.assertRaises(RuntimeError) as caught:
                    backend.generate("sys", "user")
        self.assertEqual(content, '{"ok":true}')
        self.assertEqual(FakeHTTPS.seen[0]["headers"]["Authorization"], "Bearer " + key)
        self.assertNotIn(key, FakeHTTPS.seen[0]["body"].decode())
        evidence = [p.read_text() for p in run_dir.iterdir()]
        self.scan(
            key,
            self.ledger.path.read_text(),
            json.dumps(receipt),
            json.dumps(backend.last_receipt),
            *evidence,
            str(caught.exception),
            repr(caught.exception),
            repr(backend),
            repr(backend._factory()[0]),
            repr(config),
            repr(self.ledger.__dict__),
            repr(backend.__dict__),
        )
        # Nothing under the test root holds the key either.
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(key.encode(), path.read_bytes(), path.name)

    def test_http_error_status_is_ledgered_without_body_or_key(self):
        key = throwaway()

        class Denied(FakeHTTPS):
            def getresponse(self):
                return NS(
                    status=401, read=lambda n: b'{"error":"' + key.encode() + b'"}'
                )

        with (
            patch.dict(os.environ, {"XAI_API_KEY": key}),
            patch("chaos.xai.http.client.HTTPSConnection", Denied),
        ):
            backend = xai.build(
                resolve("xai", MODEL), self.ledger, run_id="r", surface="c"
            )
            with self.assertRaises(RuntimeError) as caught:
                backend.generate("s", "u")
        self.assertEqual(str(caught.exception), "xAI HTTP status 401")
        row = self.ledger.rows()[-1]
        self.assertEqual((row["status"], row["http_status"]), ("failed", 401))
        self.assertNotIn(key, self.ledger.path.read_text())


if __name__ == "__main__":
    unittest.main()
