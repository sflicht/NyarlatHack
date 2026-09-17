"""History CLI tests never initialize a real provider."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from chaos.__main__ import main
from chaos.oauth import OAuthBackend
import test_history as fixtures
from test_episodes import wire


class HistoryCLITests(unittest.TestCase):
    def test_random_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            events = Path(directory) / "events.jsonl"
            events.write_bytes(wire(*fixtures.HistoryTests().rows()))
            events.chmod(0o600)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "history",
                        "--run-dir",
                        directory,
                        "--backend",
                        "random",
                        "--ordinary-food",
                        "--install-only",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["submitted"], 1)

    def test_missing_ledger_no_files_or_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            factory = Mock(side_effect=AssertionError("no provider"))
            transports = []

            def construct(*args, **kwargs):
                transport = OAuthBackend(*args, client_factory=factory, **kwargs)
                transports.append(transport)
                return transport

            with (
                patch("chaos.oauth.OAuthBackend", side_effect=construct),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                try:
                    code = main(
                        [
                            "history",
                            "--run-dir",
                            directory,
                            "--backend",
                            "oauth",
                            "--model-ledger",
                            str(Path(directory) / "missing"),
                        ]
                    )
                except SystemExit:
                    code = -1
            self.assertEqual(code, 2)
            self.assertEqual(len(transports), 1)
            self.assertIs(transports[0].factory, factory)
            factory.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_existing_ledger_limit_retained_and_missing_race_fails(self):
        import test_oauth as oauth_fixtures

        fixture = oauth_fixtures.OAuthTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tmp.cleanup)
        OAuthBackend(fixture.ledger, client_factory=fixture.factory).generate("s", "u")
        transport = OAuthBackend(
            fixture.ledger, require_existing=True, client_factory=fixture.factory
        )
        transport.generate("s", "u")
        data = json.loads(fixture.ledger.read_bytes())
        self.assertEqual(data["limit"], 20)
        self.assertEqual(data["attempts"], 2)
        transport.preflight()
        fixture.ledger.rename(fixture.ledger.with_suffix(".saved"))
        with self.assertRaises(FileNotFoundError):
            transport._ledger_update(lambda data: None)
        self.assertFalse(fixture.ledger.exists())
        self.assertEqual(len(fixture.calls), 2)

    def test_require_existing_cannot_create_allowance(self):
        with tempfile.TemporaryDirectory() as directory:
            factory = Mock(side_effect=AssertionError("no provider"))
            transport = OAuthBackend(
                Path(directory) / "missing",
                require_existing=True,
                client_factory=factory,
            )
            with self.assertRaises(FileNotFoundError):
                transport.generate("instructions", "prompt")
            factory.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])
