"""Slice 2b offline: history grounding, seeded layer, truthfulness, authoring
evidence and the replay backend. Fake transports and a fake validator only; no
provider, no Hermes, no native library."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import uuid

from chaos import curio, curio_author, curio_replay, curio_truth, xai
from chaos.author_config import resolve
from chaos.history import public_context, snapshot_history

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "docs/evidence/door-reluctance-1/capture/events.jsonl"
MODEL = "grok-test-model"  # fixture id; real runs pass --author-model
SOURCE = (
    "return {name='Offline counter',"
    "inspect=function(c) return 'A plain counter with three stages.' end,"
    "apply=function(c) return {text='First stage.',state=1,sanity_delta=0} end}"
)


def envelope(source=SOURCE, note="handwritten fixture"):
    return json.dumps({"lua_source": source, "continuity_note": note})


def private_events(root, source=HISTORY, extra=None):
    """A private run directory holding one checked native history."""
    d = Path(root) / ("events-" + uuid.uuid4().hex[:8])
    d.mkdir(mode=0o700)
    shutil.copyfile(source, d / "events.jsonl")
    os.chmod(d / "events.jsonl", 0o600)
    for name, text in (extra or {}).items():
        (d / name).write_text(text)
        os.chmod(d / name, 0o600)
    return d


class FakeClient:
    def __init__(self, content):
        self.base_url = xai.XAI_BASE_URL
        self.content = content
        self.calls = []
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return NS(
            model=MODEL,
            choices=[NS(message=NS(content=self.content, tool_calls=None))],
            usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    def close(self):
        pass


class FakeValidator:
    """Stands in for chaos.curio_native.CurioValidator (no native library)."""

    library_sha256 = "0" * 64

    def __init__(self, admitted=True, texts=("A plain counter with three stages.",)):
        self.admitted = admitted
        self.texts = list(texts)
        self.calls = []

    def validate(self, source, sanity, insight):
        self.calls.append((source, sanity, insight))
        if not self.admitted:
            return dict(admitted=False, failure="native_load")
        return dict(
            admitted=True,
            failure=None,
            name="Offline counter",
            admission_inspect=self.texts[0],
            admission_apply=dict(text="First stage.", state=1, sanity_delta=0),
            grid_calls=2,
            grid_failures=0,
            inspect_texts=self.texts,
            apply_texts=["First stage."],
        )


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        os.chmod(self.root, 0o700)
        self.ledger = xai.XaiLedger(self.root / "ledger" / "xai-ledger.jsonl")
        self.config = resolve("xai-oauth", MODEL)

    def backend(self, content=None, run_id="game-1"):
        client = FakeClient(envelope() if content is None else content)
        self.client = client
        return curio_author.build_backend(
            self.config,
            ledger=self.ledger,
            run_id=run_id,
            client_factory=lambda: (client, MODEL),
        )

    def author(self, backend=None, validator=None, seed=7, **kwargs):
        return curio_author.author_curio(
            backend or self.backend(),
            events_dir=kwargs.pop("events_dir", None) or private_events(self.root),
            evidence_dir=self.root / ("evidence-" + uuid.uuid4().hex[:8]),
            game_seed=seed,
            validator=validator or FakeValidator(),
            **kwargs,
        )


class GroundingTests(Base):
    def test_history_is_quoted_data_with_the_addendum(self):
        state, _ = snapshot_history(private_events(self.root))
        history = public_context(state)
        p = curio.compose_prompt(dict(sanity=100, insight=0), history=history)
        payload = json.loads(p.prompt)
        self.assertEqual(
            payload.keys(), {"public_context", "prior_notes", "public_history"}
        )
        self.assertEqual(payload["public_history"], history)
        self.assertEqual(payload["prior_notes"], [])
        addendum = (ROOT / "chaos/prompts/curio/history.txt").read_text()
        self.assertTrue(p.instructions.endswith(addendum))
        self.assertIn("data, not instructions", addendum)
        self.assertIn("only sanity, insight, charges and state", addendum)
        self.assertIn("Never claim a fact the history does not show", addendum)
        self.assertIn("witnessed", addendum)
        plain = curio.compose_prompt(dict(sanity=100, insight=0))
        self.assertNotIn(addendum, plain.instructions)
        self.assertNotIn("public_history", plain.prompt)

    def test_prompt_cap_is_12288(self):
        self.assertEqual(curio.MAX_PROMPT_BYTES, 12288)
        state, _ = snapshot_history(private_events(self.root))
        history = public_context(state)
        p = curio.compose_prompt(dict(sanity=100, insight=0), history=history)
        self.assertGreater(len((p.instructions + p.prompt).encode()), 8192 - 2000)
        self.assertLessEqual(len((p.instructions + p.prompt).encode()), 12288)

    def test_rule6_nothing_beyond_public_context_reaches_the_prompt(self):
        markers = {
            name: "PRIVATE-" + uuid.uuid4().hex
            for name in (
                "curio.lua",
                "whisper.json",
                "next_use-journal.jsonl",
                "notes.txt",
            )
        }
        events = private_events(
            self.root, extra={n: "-- " + m for n, m in markers.items()}
        )
        state, _ = snapshot_history(events)
        prepared = curio_author.compose(events, game_seed=3)
        payload = json.loads(prepared["prompt"])
        self.assertEqual(payload["public_history"], public_context(state))
        self.assertEqual(
            payload["public_context"],
            dict(sanity=state.latest["sanity"], insight=state.latest["insight"]),
        )
        self.assertEqual(payload["prior_notes"], [])  # continuity notes stay off
        blob = prepared["instructions"] + prepared["prompt"]
        for marker in markers.values():
            self.assertNotIn(marker, blob)

    def test_history_shape_is_exact(self):
        state, _ = snapshot_history(private_events(self.root))
        history = public_context(state)
        for bad in (
            dict(history, extra=1),
            {k: v for k, v in history.items() if k != "episodes"},
            dict(history, history_context_v=2),
            [history],
        ):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                curio.compose_prompt(dict(sanity=1, insight=0), history=bad)
        big = dict(history, summary=dict(history["summary"], pad="x" * 7000))
        with self.assertRaisesRegex(ValueError, "history context byte cap"):
            curio.compose_prompt(dict(sanity=1, insight=0), history=big)


class SeededLayerTests(unittest.TestCase):
    def test_sha256_rule_and_replayable_across_processes(self):
        for seed in (0, 1, 7, 23, 41, 2**63 - 1):
            digest = hashlib.sha256(b"nyarlathack-curio-layer-v1:%d" % seed).digest()
            expected = curio.LAYERS[int.from_bytes(digest[:8], "big") % 8]
            self.assertEqual(curio.seeded_layer(seed), expected)
        code = (
            "from chaos import curio; print([curio.seeded_layer(s) for s in range(40)])"
        )
        outputs = {
            subprocess.run(
                [sys.executable, "-c", code],
                cwd=ROOT,
                env=dict(os.environ, PYTHONHASHSEED=salt),
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for salt in ("1", "2", "random")
        }
        self.assertEqual(len(outputs), 1)
        self.assertEqual(
            set(curio.seeded_layer(s) for s in range(200)), set(curio.LAYERS)
        )
        self.assertEqual(sorted(curio.LAYERS), sorted(curio._LITERARY_FILES))

    def test_invalid_seeds(self):
        for bad in (-1, 2**63, True, 1.0, "7", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                curio.seeded_layer(bad)


class TruthTests(unittest.TestCase):
    FALSE = {
        "items": "A gold piece drops into your hand.",
        "teleports": "It whisks you away to another floor.",
        "damage": "The rim burns you.",
        "monsters": "Your dog comes when it sounds.",
        "future": "You will find a key below.",
        "stats": "You gain insight from its hum.",
        "witness": "The whistle remembers your face.",
    }
    HONEST = (
        "A plain counter with three stages.",
        "You will not call it a message.",
        "Another look does not summon agreement.",
        "Your thoughts steady for a moment.",
        "It sounds once, thinly, and is cold.",
    )

    def test_each_category_is_caught_and_honest_text_passes(self):
        for category, text in self.FALSE.items():
            with self.subTest(category=category):
                hits = curio_truth.check([text])
                self.assertTrue(hits)
                self.assertIn(category, {h["category"] for h in hits})
        for text in self.HONEST:
            with self.subTest(text=text):
                self.assertEqual(curio_truth.check([text]), [])

    def test_rules_come_from_the_data_file(self):
        data = json.loads(curio_truth.RULES_FILE.read_text())
        self.assertEqual(data["version"], 1)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rules.json"
            path.write_text(
                json.dumps(
                    dict(version=1, rules=[dict(id="x", category="c", pattern="plain")])
                )
            )
            rules = curio_truth.load_rules(path)
        self.assertTrue(curio_truth.check(["A plain counter"], rules))
        self.assertEqual(curio_truth.check(["The rim burns you."], rules), [])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "rules.json"
            path.write_text(json.dumps(dict(version=2, rules=[])))
            with self.assertRaises(ValueError):
                curio_truth.load_rules(path)

    def test_curio_texts_covers_name_and_every_grid_text(self):
        v = FakeValidator(texts=["a", "b"]).validate(b"x", 1, 0)
        self.assertEqual(
            curio_truth.curio_texts(v), ["Offline counter", "a", "First stage.", "b"]
        )


class AuthoringTests(Base):
    def files(self, receipt_dir):
        return sorted(p.name for p in Path(receipt_dir).iterdir())

    def test_ready_curio_writes_the_full_evidence(self):
        validator = FakeValidator()
        events = private_events(self.root)
        evidence = self.root / "evidence"
        receipt = curio_author.author_curio(
            self.backend(),
            events_dir=events,
            evidence_dir=evidence,
            game_seed=7,
            validator=validator,
        )
        self.assertEqual(receipt["outcome"], "ready")
        self.assertEqual(
            self.files(evidence),
            ["prompt.json", "raw-response.txt", "receipt.json", "source.lua"],
        )
        raw = (evidence / "raw-response.txt").read_bytes()
        self.assertEqual(raw, envelope().encode())
        self.assertEqual(
            receipt["raw_response_sha256"], hashlib.sha256(raw).hexdigest()
        )
        self.assertEqual((evidence / "source.lua").read_bytes(), SOURCE.encode())
        self.assertEqual(
            receipt["lua_source_sha256"], hashlib.sha256(SOURCE.encode()).hexdigest()
        )
        self.assertEqual(receipt["layer"], curio.seeded_layer(7))
        prepared = json.loads((evidence / "prompt.json").read_text())
        self.assertEqual(
            receipt["prompt_sha256"],
            hashlib.sha256(
                (prepared["instructions"] + "\0" + prepared["prompt"]).encode()
            ).hexdigest(),
        )
        state, _ = snapshot_history(events)
        canonical = json.dumps(
            public_context(state), sort_keys=True, separators=(",", ":")
        )
        self.assertEqual(
            receipt["public_context_sha256"],
            hashlib.sha256(canonical.encode()).hexdigest(),
        )
        self.assertEqual(receipt["provider"], "xai-oauth")
        self.assertEqual(receipt["model"], MODEL)
        self.assertEqual(receipt["transport"]["route"], "hermes-xai-oauth")
        self.assertEqual(receipt["transport"]["record"]["status"], "completed")
        self.assertEqual(
            receipt["transport"]["record"]["prompt_sha256"], receipt["prompt_sha256"]
        )
        rows = self.ledger.rows()
        self.assertEqual([r["status"] for r in rows], ["reserved", "completed"])
        self.assertEqual(rows[0]["surface"], "curio")
        self.assertEqual(validator.calls[0][0], SOURCE.encode())
        self.assertEqual(curio_author.read_evidence(evidence), receipt)
        sent = self.client.calls[0]["messages"]
        self.assertEqual(sent[0]["content"], prepared["instructions"])
        self.assertEqual(sent[1]["content"], prepared["prompt"])

    def test_six_minute_deadline_reaches_the_transport(self):
        backend = self.backend()
        self.author(backend)
        self.assertEqual(curio_author.DEADLINE_S, 360)
        self.assertEqual(backend.timeout, 360)
        self.assertLess(backend.deadline, float("inf"))
        with self.assertRaises(ValueError):
            self.author(deadline_s=361)

    def test_rejections_are_recorded_and_never_ready(self):
        cases = (
            ("not json", FakeValidator(), "envelope_rejected"),
            (envelope(), FakeValidator(admitted=False), "native_rejected"),
            (
                envelope(),
                FakeValidator(texts=["It whisks you away to another floor."]),
                "truth_rejected",
            ),
        )
        for content, validator, outcome in cases:
            with self.subTest(outcome=outcome):
                evidence = self.root / ("e-" + outcome)
                receipt = curio_author.author_curio(
                    self.backend(content, run_id="g-" + outcome),
                    events_dir=private_events(self.root),
                    evidence_dir=evidence,
                    game_seed=1,
                    validator=validator,
                )
                self.assertEqual(receipt["outcome"], outcome)
                self.assertTrue((evidence / "raw-response.txt").exists())
                with self.assertRaisesRegex(ValueError, "only a ready curio"):
                    curio_author.read_evidence(evidence)
                with self.assertRaises(ValueError):
                    curio_author.install(self.root / "nowhere", evidence, safe=0)
        truth = json.loads((self.root / "e-truth_rejected/receipt.json").read_text())
        self.assertEqual(truth["truth_hits"][0]["category"], "teleports")

    def test_transport_failure_is_ledgered_and_recorded(self):
        backend = self.backend()

        def broken():
            raise xai.NoModelReachable("xai-oauth: no Hermes xAI OAuth login")

        backend._factory = broken
        evidence = self.root / "e-transport"
        receipt = curio_author.author_curio(
            backend,
            events_dir=private_events(self.root),
            evidence_dir=evidence,
            game_seed=1,
            validator=FakeValidator(),
        )
        self.assertEqual(receipt["outcome"], "transport_failed")
        self.assertEqual(receipt["error_type"], "NoModelReachable")
        self.assertEqual(self.files(evidence), ["prompt.json", "receipt.json"])
        self.assertEqual(
            [r["status"] for r in self.ledger.rows()], ["reserved", "failed"]
        )

    def test_tampered_evidence_fails_verification(self):
        receipt = self.author()
        evidence = next(self.root.glob("evidence-*"))
        self.assertEqual(curio_author.read_evidence(evidence), receipt)
        for name, data in (
            ("source.lua", SOURCE.replace("First", "Other").encode()),
            ("raw-response.txt", envelope(note="changed").encode()),
        ):
            with self.subTest(name=name):
                copy = self.root / ("copy-" + name)
                shutil.copytree(evidence, copy)
                os.chmod(copy / name, 0o600)
                (copy / name).write_bytes(data)
                with self.assertRaises(ValueError):
                    curio_author.read_evidence(copy)

    def test_nothing_configured_builds_nothing(self):
        self.assertIsNone(
            curio_author.build_backend(None, ledger=self.ledger, run_id="game-1")
        )

    def test_openai_codex_still_goes_through_oauth_backend(self):
        from chaos.oauth import CURIO_PURPOSE, OAuthBackend

        config = resolve("openai-codex", "gpt-test-model")
        client = NS(
            base_url="https://chatgpt.com/backend-api/codex",
            _real_client=NS(max_retries=2),
            close=lambda: None,
        )

        def create(**kwargs):
            return NS(
                model="gpt-test-model",
                choices=[NS(message=NS(content=envelope(), tool_calls=None))],
                usage=NS(input_tokens=20, output_tokens=5, total_tokens=25),
            )

        client.chat = NS(completions=NS(create=create))
        ledger_dir = self.root / "codex"
        ledger_dir.mkdir(mode=0o700)
        backend = curio_author.build_backend(
            config,
            ledger=ledger_dir / "calls.json",
            run_id="game-1",
            client_factory=lambda: (client, "gpt-test-model"),
            fresh_ledger=True,
        )
        self.assertIs(type(backend), OAuthBackend)
        self.assertEqual(backend.purpose, CURIO_PURPOSE)
        receipt = self.author(backend)
        self.assertEqual(receipt["outcome"], "ready")
        self.assertEqual(receipt["provider"], "openai-codex")
        self.assertEqual(receipt["transport"]["record"]["status"], "completed")


class KeyNeverLeaksTests(Base):
    def test_api_key_never_reaches_curio_evidence(self):
        key = "t" + uuid.uuid4().hex + uuid.uuid4().hex
        seen = []

        class FakeHTTPS:
            def __init__(self, host, port, timeout):
                pass

            def request(self, method, path, body, headers):
                seen.append(headers)

            def getresponse(self):
                body = json.dumps(
                    dict(
                        model=MODEL,
                        choices=[dict(message=dict(content=envelope()))],
                        usage=dict(
                            prompt_tokens=3, completion_tokens=2, total_tokens=5
                        ),
                    )
                ).encode()
                return NS(status=200, read=lambda n: body)

            def close(self):
                pass

        config = resolve("xai", MODEL)
        evidence = self.root / "evidence"
        with (
            patch.dict(os.environ, {"XAI_API_KEY": key}),
            patch("chaos.xai.http.client.HTTPSConnection", FakeHTTPS),
        ):
            backend = curio_author.build_backend(
                config, ledger=self.ledger, run_id="game-1"
            )
            receipt = curio_author.author_curio(
                backend,
                events_dir=private_events(self.root),
                evidence_dir=evidence,
                game_seed=2,
                validator=FakeValidator(),
            )
            run = self.root / "run"
            run.mkdir(mode=0o700)
            curio_author.install(run, evidence, safe=0)
        self.assertEqual(receipt["outcome"], "ready")
        self.assertEqual(seen[0]["Authorization"], "Bearer " + key)
        for text in (json.dumps(receipt), repr(backend), repr(backend.__dict__)):
            self.assertNotIn(key, text)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(key.encode(), path.read_bytes(), path.name)


class ReplayTests(Base):
    def ready(self, safe=4):
        receipt = self.author()
        evidence = next(self.root.glob("evidence-*"))
        run = self.root / "run"
        run.mkdir(mode=0o700)
        record = curio_author.install(run, evidence, safe=safe)
        self.assertEqual(
            record, dict(v=1, safe=safe, source_sha256=receipt["lua_source_sha256"])
        )
        self.assertEqual((run / "curio.lua").read_bytes(), SOURCE.encode())
        return evidence

    def test_replay_installs_logged_source_at_logged_safe_point(self):
        evidence = self.ready(safe=4)
        replay = curio_replay.CurioReplayBackend(evidence)
        run = self.root / "replay-run"
        run.mkdir(mode=0o700)
        with patch.object(xai.XaiBackend, "generate", side_effect=AssertionError):
            self.assertFalse(replay.due(3))
            self.assertTrue(replay.due(4))
            receipt = replay.install(run)
        self.assertEqual((run / "curio.lua").read_bytes(), SOURCE.encode())
        self.assertEqual(
            receipt["source_sha256"], hashlib.sha256(SOURCE.encode()).hexdigest()
        )
        self.assertFalse(replay.due(5))
        with self.assertRaises(ValueError):
            replay.install(run)
        # The engine's own curio-used.lua is the cross-check.
        (run / "curio-used.lua").write_bytes(SOURCE.encode())
        os.chmod(run / "curio-used.lua", 0o600)
        self.assertEqual(replay.verify(run), receipt)
        os.chmod(run / "curio-used.lua", 0o600)
        (run / "curio-used.lua").write_bytes(b"return {}")
        with self.assertRaisesRegex(ValueError, "curio-used.lua"):
            replay.verify(run)

    def test_replay_that_passes_the_safe_point_diverges(self):
        replay = curio_replay.CurioReplayBackend(self.ready(safe=2))
        with self.assertRaises(curio_replay.ReplayDiverged):
            replay.due(3)

    def test_replay_never_imports_a_transport(self):
        code = (
            "import sys; import chaos.curio_replay; "
            "bad = [m for m in sys.modules if m in ('chaos.xai', 'chaos.oauth') "
            "or m.split('.')[0] in ('agent', 'openai', 'hermes_bootstrap')]; "
            "print(bad)"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(out.stdout.strip(), "[]")


class HermesReexecTests(Base):
    """Slice 3 builds the xai-oauth backend at director startup: importing
    Hermes may os.execv the interpreter, so it must happen before any run
    state, ledger reservation or evidence exists."""

    def test_hermes_is_imported_when_the_backend_is_built_not_per_request(self):
        imports = []

        def builder(model):
            return FakeClient(envelope()), model

        module = NS(_build_xai_oauth_aux_client=builder)

        class Finder:
            def find_module(self, name, path=None):
                return None

        with patch.dict(sys.modules, {"agent": NS(), "agent.auxiliary_client": module}):
            real_import = __import__

            def tracking(name, *args, **kwargs):
                if name == "agent.auxiliary_client":
                    imports.append(
                        len(self.ledger.path.exists() and self.ledger.rows() or [])
                    )
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", tracking):
                backend = curio_author.build_backend(
                    self.config, ledger=self.ledger, run_id="game-1"
                )
            self.assertEqual(imports, [0])  # at build, before any ledger row
            self.assertFalse(self.ledger.path.exists())
            with patch("builtins.__import__", tracking):
                receipt = self.author(backend)
        self.assertEqual(receipt["outcome"], "ready")
        self.assertEqual(imports, [0])  # never again per request


if __name__ == "__main__":
    unittest.main()
