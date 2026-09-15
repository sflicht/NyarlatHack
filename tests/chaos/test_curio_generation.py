"""Synthetic API objects/native-shaped events only; never live authorship evidence."""

import builtins
import importlib
import json

from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from chaos import curio_continuity as continuity, curio_store as store
from chaos.oauth import MODEL, OAuthBackend

# Neutral hand-written hook fixture, NOT generated literary production content.
SOURCE = (
    'return {name="Test", inspect=function(c) return "Test" end, '
    'apply=function(c) return {text="Test",state=c.state,sanity_delta=0} end}\r\n'
)
RAW = (
    " \n"
    + json.dumps(
        dict(lua_source=SOURCE, continuity_note="Synthetic note é"), ensure_ascii=False
    )
    + "\n "
)


def put(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def event(**changes):
    value = dict(
        v=1,
        seq=1,
        turn=1,
        safe=0,
        sanity=100,
        insight=0,
        budget=1,
        spent=0,
        reserved=0,
        last_id=0,
        event="session",
        phase="result",
        detail="new",
    )
    value.update(changes)
    return json.dumps(value).encode() + b"\n"


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("chaos.curio_generation"),
            "bounded generation service missing",
        )
        self.api = importlib.import_module("chaos.curio_generation")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundles = self.root / "bundles"
        self.journal = self.root / "journal"
        self.run_dir = self.root / "run"
        for p in (self.bundles, self.journal, self.run_dir):
            p.mkdir(mode=0o700)
        continuity.create_journal(self.journal)
        self.events = self.run_dir / "events.jsonl"
        put(self.events, event())
        self.output = self.root / "attempt"
        self.ledger = self.root / "authorization.json"
        self.calls = []
        self.factories = 0
        self.closed = 0
        self.response = NS(
            model=MODEL,
            choices=[NS(message=NS(content=RAW, tool_calls=None))],
            usage=NS(input_tokens=11, output_tokens=7, total_tokens=18),
        )
        self.client = NS(
            base_url="https://chatgpt.com/backend-api/codex",
            _real_client=NS(max_retries=99),
            close=self.close,
            chat=NS(completions=NS(create=self.create)),
        )
        original_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name == "agent" or name.startswith("agent."):
                raise AssertionError("credential imports forbidden in offline tests")
            return original_import(name, *args, **kwargs)

        self.guard = patch("builtins.__import__", side_effect=guarded)
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def close(self):
        self.closed += 1

    def factory(self):
        self.factories += 1
        self.assertTrue((self.output / "prepared.json").exists())
        self.assertEqual(self.data()["records"][-1]["status"], "reserved")
        self.assertEqual(self.data()["records"][-1]["purpose"], "curio-generation")
        return self.client, MODEL

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self.assertEqual(self.client._real_client.max_retries, 0)
        self.assertEqual(self.data()["records"][-1]["status"], "reserved")
        return self.response

    def data(self):
        return json.loads(self.ledger.read_bytes())

    def generate(self, **changes):
        args = dict(
            event_file=self.events,
            output_directory=self.output,
            bundle_root=self.bundles,
            journal_root=self.journal,
            ledger=self.ledger,
            fresh_ledger=True,
            client_factory=self.factory,
        )
        args.update(changes)
        return self.api.generate_curio(**args)

    def rejected_before_factory(self, **changes):
        with self.assertRaises((ValueError, OSError)):
            self.generate(**changes)
        self.assertEqual(self.factories, 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.ledger.exists())

    def test_exact_bundle_receipt_public_projection_and_read_only_inspection(self):
        # Arbitrary details/extra fields must never enter the prompt.
        put(
            self.events,
            event()
            + event(
                seq=2,
                event="sanity",
                detail="SECRET_DETAIL",
                sanity=63,
                insight=4,
                hidden="SECRET_MAP",
            ),
        )
        receipt = self.generate()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.closed, 1)
        call = self.calls[0]
        self.assertEqual(call["model"], MODEL)
        self.assertEqual(call["tools"], [])
        self.assertLessEqual(call["timeout"], 60)
        payload = json.loads(call["messages"][1]["content"])
        self.assertEqual(
            payload, dict(public_context=dict(sanity=63, insight=4), prior_notes=[])
        )
        self.assertNotIn("SECRET", str(call))
        self.assertNotIn(str(self.root), str(call))
        self.assertEqual((self.output / "raw-response.json").read_bytes(), RAW.encode())
        candidate = store.read_candidate(self.bundles, receipt["source_sha256"])
        self.assertEqual(candidate.lua_source, SOURCE.encode())
        self.assertEqual(candidate.raw_response, RAW)
        self.assertEqual(receipt["raw_response_sha256"], store._digest(RAW.encode()))
        self.assertEqual(receipt["status"], "candidate_stored_registered_not_installed")
        self.assertEqual(receipt["transport"]["record_index"], 0)
        self.assertEqual(receipt["transport"]["record"], self.data()["records"][0])
        self.assertEqual(receipt["transport"]["record"]["status"], "completed")
        prompt_hash = store._digest(
            (
                call["messages"][0]["content"] + "\0" + call["messages"][1]["content"]
            ).encode()
        )
        self.assertEqual(receipt["transport"]["record"]["prompt_sha256"], prompt_hash)
        self.assertEqual(continuity.prior_notes(self.journal)[0]["status"], "authored")
        self.assertFalse((self.run_dir / "curio.lua").exists())
        with patch("os.fsync", side_effect=AssertionError("inspection writes")):
            self.assertEqual(self.api.read_generation(self.output), receipt)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises((ValueError, OSError)):
            self.generate()
        self.assertEqual(len(self.calls), 1)

    def test_invalid_histories_before_factory(self):
        cases = [
            b"",
            event()[:-1],
            event(seq=2),
            event(detail="restore"),
            event(spent=1),
            event(sanity=True),
            event(insight=1000001),
            event() + event(seq=3),
            event(turn=5) + event(seq=2, detail="restore", turn=4),
            event() + event(seq=2, event="death") + event(seq=3, detail="restore"),
            b"x" * (continuity.MAX_EVENT_BYTES + 1),
            event() + b"{}\n",
            b'{"v":1,"v":1}\n',
        ]
        for raw in cases:
            with self.subTest(raw=raw[:100]):
                put(self.events, raw)
                self.rejected_before_factory()

    def test_preflight_paths_permissions_partial_and_conflicts(self):
        for name in (
            "curio.lua",
            "curio-used.lua",
            "curio-install.json",
            ".curio-crash",
        ):
            p = self.run_dir / name
            put(p, b"conflict")
            self.rejected_before_factory()
            p.unlink()
        self.events.chmod(0o644)
        self.rejected_before_factory()
        self.events.chmod(0o600)
        self.output.mkdir(mode=0o700)
        self.rejected_before_factory()
        self.output.rmdir()
        partial = self.bundles / ("a" * 64)
        partial.mkdir(mode=0o700)
        self.rejected_before_factory()
        partial.rmdir()
        self.bundles.chmod(0o755)
        self.rejected_before_factory()

    def test_bad_notes_old_conflicting_source_and_partial_journal(self):
        c = store.store_candidate(self.bundles, RAW)
        continuity.register(self.journal, self.bundles, c.candidate_id)
        put(self.bundles / c.candidate_id / "source.lua", b"bad")
        self.rejected_before_factory()
        put(self.bundles / c.candidate_id / "source.lua", c.lua_source)
        (self.journal / "000001.commit").unlink()
        self.rejected_before_factory()

    def test_notes_are_verified_host_status_not_model_prose(self):
        c = store.store_candidate(
            self.bundles,
            json.dumps(
                dict(lua_source="-- prior", continuity_note="placed: only prose")
            ),
        )
        continuity.register(self.journal, self.bundles, c.candidate_id)
        self.generate()
        notes = json.loads(self.calls[0]["messages"][1]["content"])["prior_notes"]
        self.assertEqual(
            notes,
            [
                dict(
                    candidate_id=c.candidate_id,
                    status="authored",
                    continuity_note="placed: only prose",
                )
            ],
        )

    def test_full_prompt_cap_before_factory(self):
        for n in range(6):
            raw = json.dumps(
                dict(lua_source=f"-- synthetic {n}", continuity_note="é" * 256)
            )
            c = store.store_candidate(self.bundles, raw)
            continuity.register(self.journal, self.bundles, c.candidate_id)
        # Trusted resource expansion, not an opaque backend/prompt bypass.
        from chaos import curio

        real_read = Path.read_text

        def read(path, *args, **kw):
            if path == curio._PROMPTS / "contract.txt":
                return "x" * 8192
            return real_read(path, *args, **kw)

        with patch.object(Path, "read_text", read):
            self.rejected_before_factory()

    def test_invalid_envelope_keeps_exact_diagnostic_no_candidate(self):
        self.response.choices[
            0
        ].message.content = ' \n{"lua_source":"x","status":"placed"}\n'
        with self.assertRaises(ValueError):
            self.generate()
        self.assertEqual(
            (self.output / "raw-response.json").read_bytes(),
            self.response.choices[0].message.content.encode(),
        )
        self.assertEqual(list(self.bundles.iterdir()), [])
        self.assertEqual(continuity.prior_notes(self.journal), [])
        self.assertEqual(self.data()["records"][0]["status"], "completed")
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["stage"], "envelope")
        self.assertEqual(failure["last_known_transport"]["record_index"], 0)
        self.assertEqual(
            failure["last_known_transport"]["record"], self.data()["records"][0]
        )
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises((ValueError, OSError)):
            self.generate()
        self.assertEqual(len(self.calls), 1)

    def test_backend_rejections_no_manufactured_response(self):
        for case in ("model", "tool", "oversize", "nontext", "choices"):
            with self.subTest(case=case):
                self.output = self.root / case
                self.ledger = self.root / (case + ".json")
                self.response = NS(
                    model=MODEL,
                    usage=NS(),
                    choices=[NS(message=NS(content=RAW, tool_calls=None))],
                )
                if case == "model":
                    self.response.model = "other"
                if case == "tool":
                    self.response.choices[0].message.tool_calls = ["tool"]
                if case == "oversize":
                    self.response.choices[0].message.content = "x" * 8193
                if case == "nontext":
                    self.response.choices[0].message.content = None
                if case == "choices":
                    self.response.choices = []
                with self.assertRaises(ValueError):
                    self.generate()
                self.assertFalse((self.output / "raw-response.json").exists())
                self.assertEqual(self.data()["records"][0]["status"], "failed")
        self.assertEqual(len(self.calls), 5)

    def test_missing_auth_and_wrong_route_consume_without_api(self):
        def unavailable():
            self.factory()
            raise RuntimeError("synthetic auth failure; secret must not be copied")

        with self.assertRaises(RuntimeError):
            self.generate(client_factory=unavailable)
        self.assertEqual(self.data()["records"][0]["status"], "failed")
        self.assertNotIn(
            "secret", str(list(p.read_bytes() for p in self.output.iterdir()))
        )
        self.output = self.root / "wrong-route"
        self.client.base_url = "https://api.openai.com/v1"
        with self.assertRaises(ValueError):
            self.generate(fresh_ledger=False)
        self.assertEqual(self.data()["attempts"], 2)
        self.assertEqual(len(self.calls), 0)
        self.output = self.root / "exhausted"
        before = self.factories
        with self.assertRaises(ValueError):
            self.generate(fresh_ledger=False)
        self.assertEqual(self.factories, before)

    def test_output_sync_failure_no_factory_no_attempt(self):
        with patch("chaos.curio_store.os.fsync", side_effect=OSError("synthetic sync")):
            self.rejected_before_factory()
        self.assertTrue(self.output.exists())
        self.rejected_before_factory()

    def test_reservation_sync_failure_no_factory_or_api(self):
        original = OAuthBackend._ledger_update

        def update(backend, fn, **kw):
            if kw.get("write", True):
                with patch(
                    "os.fsync", side_effect=OSError("synthetic reservation sync")
                ):
                    return original(backend, fn, **kw)
            return original(backend, fn, **kw)

        with patch.object(OAuthBackend, "_ledger_update", update):
            with self.assertRaises(OSError):
                self.generate()
        self.assertEqual(self.factories, 0)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.output / "raw-response.json").exists())

    def test_storage_and_registration_failure_do_not_retry_or_refund(self):
        for target in ("store_candidate", "register"):
            with self.subTest(target=target):
                self.output = self.root / target
                self.ledger = self.root / (target + ".json")
                module = store if target == "store_candidate" else continuity
                with patch.object(
                    module, target, side_effect=OSError("synthetic failure")
                ):
                    with self.assertRaises(OSError):
                        self.generate()
                self.assertEqual(self.data()["attempts"], 1)
                self.assertEqual(self.data()["records"][0]["status"], "completed")
                self.assertTrue((self.output / "raw-response.json").exists())
                self.assertFalse((self.output / "complete.commit").exists())
        self.assertEqual(len(self.calls), 2)

    def test_missing_ledger_default_does_not_initialize(self):
        self.rejected_before_factory(fresh_ledger=False)

    def test_unregistered_complete_bundle_blocks_next_attempt(self):
        with patch.object(
            continuity,
            "register",
            side_effect=OSError("synthetic registration failure"),
        ):
            with self.assertRaises(OSError):
                self.generate()
        self.output = self.root / "second"
        before = self.factories
        with self.assertRaises(ValueError):
            self.generate(fresh_ledger=False)
        self.assertEqual(self.factories, before)
        self.assertEqual(self.data()["attempts"], 1)

    def test_factory_and_response_context_drift_fail_closed(self):
        original_factory = self.factory

        def changed_factory():
            result = original_factory()
            put(self.events, event(sanity=60))
            return result

        with self.assertRaises(ValueError):
            self.generate(client_factory=changed_factory)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.closed, 1)
        self.assertEqual(self.data()["records"][0]["status"], "failed")
        put(self.events, event())
        self.output = self.root / "response-drift"
        original_create = self.create

        def changed_response(**kw):
            result = original_create(**kw)
            put(self.events, event(sanity=61))
            return result

        self.client.chat.completions.create = changed_response
        with self.assertRaises(ValueError):
            self.generate(fresh_ledger=False)
        self.assertEqual((self.output / "raw-response.json").read_bytes(), RAW.encode())
        self.assertEqual(list(self.bundles.iterdir()), [])
        self.assertEqual(self.data()["records"][1]["status"], "completed")

    def test_host_identity_only_explicit_and_restore_chain(self):
        put(
            self.events,
            event(role="SECRET_ROLE") + event(seq=2, detail="restore", sanity=70),
        )
        self.generate(role="Wizard", race="human")
        public = json.loads(self.calls[0]["messages"][1]["content"])["public_context"]
        self.assertEqual(
            public, dict(sanity=70, insight=0, role="Wizard", race="human")
        )
        self.assertNotIn("SECRET_ROLE", str(self.calls))

    def test_self_hash_repair_cannot_hide_metadata_or_source_tamper(self):
        receipt = self.generate()
        prepared = (self.output / "prepared.json").read_bytes()
        generation = (self.output / "generation.json").read_bytes()
        for mutate in (
            lambda d: d.update(version=True),
            lambda d: d.update(unknown="extra"),
            lambda d: d["public_context"].update(sanity=1),
            lambda d: d.update(instructions="wrong prompt"),
            lambda d: d["journal"]["notes"].append(
                dict(candidate_id="a" * 64, status="placed", continuity_note="invented")
            ),
        ):
            data = json.loads(prepared)
            mutate(data)
            changed = store._encode(data)
            put(self.output / "prepared.json", changed)
            r = json.loads(generation)
            r["prepared_sha256"] = store._digest(changed)
            encoded = store._encode(r)
            put(self.output / "generation.json", encoded)
            put(self.output / "complete.commit", store._digest(encoded).encode())
            with self.assertRaises(ValueError):
                self.api.read_generation(self.output)
        put(self.output / "prepared.json", prepared)
        put(self.output / "generation.json", generation)
        put(self.output / "complete.commit", store._digest(generation).encode())
        put(self.bundles / receipt["source_sha256"] / "source.lua", b"changed")
        with self.assertRaises(ValueError):
            self.api.read_generation(self.output)

    def test_read_only_inspection_allows_bound_prefix_advancement(self):
        receipt = self.generate()
        put(self.events, event() + event(seq=2, event="sanity", sanity=50))
        with patch("os.fsync", side_effect=AssertionError("inspection writes")):
            self.assertEqual(self.api.read_generation(self.output), receipt)
        raw = self.events.read_bytes()
        self.events.unlink()
        put(self.events, raw)
        # A replace-created inode may be immediately reused; force a distinct one.
        replacement = self.run_dir / "replacement"
        put(replacement, raw)
        replacement.replace(self.events)
        with self.assertRaises(ValueError):
            self.api.read_generation(self.output)

    def test_overlapping_publication_paths_reject_before_reservation(self):
        for output in (
            self.bundles / "attempt",
            self.journal / "attempt",
            self.run_dir / ".curio-attempt",
            self.ledger,
        ):
            with self.subTest(output=output):
                self.rejected_before_factory(output_directory=output)
                self.assertFalse(output.exists())

    def test_exact_record_index_with_interleaved_legacy_call(self):
        original_create = self.create

        def create(**kwargs):
            result = original_create(**kwargs)
            client = NS(
                base_url="https://chatgpt.com/backend-api/codex",
                _real_client=NS(max_retries=0),
                close=lambda: None,
                chat=NS(
                    completions=NS(
                        create=lambda **kw: NS(
                            model=MODEL,
                            usage=None,
                            choices=[NS(message=NS(content="{}", tool_calls=None))],
                        )
                    )
                ),
            )
            OAuthBackend(self.ledger, client_factory=lambda: (client, MODEL)).generate(
                "legacy", "synthetic"
            )
            return result

        self.client.chat.completions.create = create
        receipt = self.generate()
        self.assertEqual(self.data()["attempts"], 2)
        self.assertEqual(receipt["transport"]["record_index"], 0)
        self.assertEqual(receipt["transport"]["record"], self.data()["records"][0])
        self.assertNotIn("purpose", self.data()["records"][1])

    def test_prior_generation_remains_readable_after_second_registration(self):
        receipt = self.generate()
        first_output = self.output
        self.output = self.root / "second"
        self.response.choices[0].message.content = json.dumps(
            dict(
                lua_source="-- Second synthetic fixture", continuity_note="Second note"
            )
        )
        second = self.generate(fresh_ledger=False)
        self.assertEqual(second["transport"]["record_index"], 1)
        with patch("os.fsync", side_effect=AssertionError("inspection writes")):
            self.assertEqual(self.api.read_generation(first_output), receipt)
            self.assertEqual(self.api.read_generation(self.output), second)

    def test_inspection_detects_changed_context_and_ledger(self):
        receipt = self.generate()
        put(self.events, event(sanity=99))
        with self.assertRaises(ValueError):
            self.api.read_generation(self.output)
        put(self.events, event())
        data = self.data()
        data["records"][0]["prompt_sha256"] = "0" * 64
        put(self.ledger, json.dumps(data).encode())
        with self.assertRaises(ValueError):
            self.api.read_generation(self.output)
        self.assertEqual(receipt["transport"]["record_index"], 0)
