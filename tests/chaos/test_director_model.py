"""LOCAL FAKE HTTP fixture, not a model or measured LLM gameplay."""

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
import tempfile
import unittest
from test_director import REQ, event, append
from chaos.director import State, run


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.requests.append((self.path, dict(self.headers), json.loads(body)))
        if self.server.delay:
            time.sleep(self.server.delay)
        self.send_response(self.server.code)
        self.send_header("Location", self.server.redirect)
        self.end_headers()
        try:
            self.wfile.write(self.server.body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("chaos.model"), "model backend missing"
        )
        from chaos.model import ModelBackend

        self.ModelBackend = ModelBackend
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.requests = []
        self.server.code = 200
        self.server.delay = 0
        self.server.redirect = "http://127.0.0.1:1/stolen"
        self.server.body = json.dumps(
            {"choices": [{"message": {"content": json.dumps(dict(REQ, at=2))}}]}
        ).encode()
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"
        os.environ["CHAOS_LOCAL_FIXTURE_KEY"] = "not-a-real-key"
        self.addCleanup(os.environ.pop, "CHAOS_LOCAL_FIXTURE_KEY", None)
        self.state = State()
        self.state.ingest(event(detail="SECRET", hidden="SECRET"))

    def backend(self, **kw):
        return self.ModelBackend(
            self.url,
            "local-fake-fixture",
            "CHAOS_LOCAL_FIXTURE_KEY",
            **dict(dict(allow_local_http=True, timeout=0.2), **kw),
        )

    def test_fixture_valid_bounded_context_and_call_cap(self):
        b = self.backend(max_calls=1)
        self.assertEqual(b.choose(self.state, 1, 2), dict(REQ, at=2))
        self.assertIsNone(b.choose(self.state, 2, 3))
        self.assertEqual(len(self.server.requests), 1)
        path, headers, payload = self.server.requests[0]
        self.assertEqual(headers["Authorization"], "Bearer not-a-real-key")
        self.assertNotIn("SECRET", json.dumps(payload))
        self.assertEqual(payload["model"], "local-fake-fixture")
        self.assertLess(len(json.dumps(payload)), 8192)

    def test_malformed_duplicate_extra_and_schedule_rejected(self):
        for content in [
            "not json",
            json.dumps(REQ),
            json.dumps(dict(REQ, at=2, id=True)),
            json.dumps(dict(REQ, at=2, command="rm")),
            json.dumps(dict(REQ, at=2))[:-1] + ',"id":1}',
        ]:
            self.server.body = json.dumps(
                {"choices": [{"message": {"content": content}}]}
            ).encode()
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.backend().choose(self.state, 1, 2)
        self.assertEqual(len(self.server.requests), 5)

    def test_no_budget_no_requests_and_no_event_hammer(self):
        self.state.ingest(event(2, budget=0, spent=2))
        self.assertIsNone(self.backend().choose(self.state, 1, 2))
        with tempfile.TemporaryDirectory() as tmp:
            run(tmp, self.backend(), max_runtime=0.06, poll=0.01)
            self.assertEqual(len(self.server.requests), 0)
            append(Path(tmp) / "events.jsonl", event())
            run(tmp, self.backend(), max_runtime=0.06, poll=0.01)
            self.assertEqual(len(self.server.requests), 1)

    def test_timeout_no_retry(self):
        self.server.delay = 0.15
        start = time.monotonic()
        with self.assertRaises((ValueError, OSError)):
            self.backend(timeout=0.03).choose(self.state, 1, 2)
        self.assertLess(time.monotonic() - start, 0.3)
        self.assertEqual(len(self.server.requests), 1)

    def test_run_deadline_limits_inflight_model_request(self):
        self.server.delay = 0.15
        with tempfile.TemporaryDirectory() as tmp:
            append(Path(tmp) / "events.jsonl", event())
            with self.assertRaises((ValueError, OSError)):
                run(tmp, self.backend(timeout=1), max_runtime=0.025, poll=0.01)
            self.assertFalse((Path(tmp) / "whisper.json").exists())
        self.assertEqual(len(self.server.requests), 1)

    def test_redirects_and_oversize_rejected(self):
        self.server.code = 302
        with self.assertRaises(ValueError):
            self.backend().choose(self.state, 1, 2)
        self.assertEqual(len(self.server.requests), 1)
        self.server.code = 200
        self.server.body = b"x" * 16385
        with self.assertRaises(ValueError):
            self.backend().choose(self.state, 1, 2)
        self.assertEqual(len(self.server.requests), 2)

    def test_explicit_endpoint_env_and_limits(self):
        for kwargs in [
            dict(allow_local_http=False),
            dict(max_calls=0),
            dict(timeout=0),
            dict(max_context=10),
            dict(max_response=0),
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.backend(**kwargs)
        for url in [
            "http://example.com/api",
            "https://user:secret@example.com/api",
            "https://example.com/api#fragment",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.ModelBackend(
                    url, "fixture", "CHAOS_LOCAL_FIXTURE_KEY", allow_local_http=True
                )
        self.assertEqual(len(self.server.requests), 0)


if __name__ == "__main__":
    unittest.main()
