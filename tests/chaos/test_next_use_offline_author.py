"""Python plumbing only. Fake parser/sandbox is NOT native admission evidence."""

import ast
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from chaos.history import HistoryState
from chaos.next_use_history import next_use_menu
from test_next_use_author_contract import CONTRACT, HANDWRITTEN_EXAMPLES
from test_director import ack, event
from test_episodes import action, enabled, session, wire

ROOT = Path(__file__).resolve().parents[2]


def fixture_sources():
    """Read the two existing C string literals, without executing native code."""
    text = (ROOT / "tests/chaos/next_use_compose_fixture.c").read_text()
    result = []
    for name in ("state_lua", "witness_lua"):
        body = re.search(r"static const char " + name + r"\[\] =\s*(.*?);", text, re.S)
        assert body is not None, name
        result.append(
            "".join(
                ast.literal_eval(s) for s in re.findall(r'"(?:[^"\\]|\\.)*"', body[1])
            ).encode()
        )
    return result


class FixtureValidator:
    """Whitelist ONLY handwritten inputs; no Lua interpreter, no native claims."""

    def __init__(self):
        self.seen = []

    def parse_author(self, raw):
        self.seen.append(raw)

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("fixture duplicate")
                result[key] = value
            return result

        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if (
            type(value) is not dict
            or type(value.get("next_use_author_v")) is not int
            or value["next_use_author_v"] != 2
        ):
            raise ValueError("fixture schema")
        if set(value) == {"next_use_author_v", "abstain"} and value["abstain"] is True:
            return None
        if (
            set(value) != {"next_use_author_v", "source"}
            or type(value["source"]) is not str
        ):
            raise ValueError("fixture schema")
        source = value["source"].encode("utf-8")
        if not 0 < len(source) <= 4096 or b"\0" in source:
            raise ValueError("fixture source cap")
        return source

    def load_source(self, source):
        if source not in fixture_sources():
            raise ValueError("fixture whitelist, NOT native sandbox validation")


def response(source):
    return (
        json.dumps(
            {"next_use_author_v": 2, "source": source.decode()}, indent=2
        ).encode()
        + b"\n"
    )


class OfflineAuthorTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("chaos.next_use_author"),
            "offline author entrypoint missing",
        )
        return importlib.import_module("chaos.next_use_author")

    def setup_run(self, fact="sound_high", prior="none", hidden="SECRET"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        rows = [enabled(), session(2, private=hidden)]
        request = dict(
            v=1, id=1, at=1, mutation="hunger_rate", value=2, duration=10, telegraph=3
        )
        if prior != "none":
            rows.append(
                ack(
                    3,
                    request,
                    sanity=60,
                    cost=3,
                    spent=3,
                    reserved=3,
                    budget=3,
                    expires=20,
                )
            )
            kind = (
                dict(event="expiry", detail="hunger_rate") if prior == "expired" else {}
            )
            rows.append(event(4, turn=21, sanity=60, spent=3, last_id=1, **kind))
        start = len(rows)
        action(rows, "whistling", fact)
        action(rows, "fountain_drink", "water_refreshed")
        for row in rows:
            row.update(sanity=60)
        if prior != "none":
            for row in rows[start:]:
                row.update(turn=21, last_id=1, spent=3, budget=3)
        else:
            for row in rows:
                row.update(budget=6)
            rows.extend(
                [
                    event(9, turn=21, sanity=60, budget=6),
                    event(10, turn=21, sanity=60, budget=6),
                ]
            )
        raw = wire(*rows)
        schedules = []
        for row in next_use_menu(HistoryState(raw)):
            if row["op"] == "quiet":
                origin = row["origin"]
                schedules.append(
                    dict(
                        next_use_schedule_v=1,
                        family=row["family"],
                        move=10,
                        level_dnum=0,
                        level_dlevel=1,
                        root=origin["root_seq"],
                        notice_seq=origin["notice_seq"],
                        end_seq=origin["end_seq"],
                    )
                )
        for name, data in (
            ("events.jsonl", raw),
            ("next_use-schedule.jsonl", wire(*schedules)),
        ):
            path = directory / name
            path.write_bytes(data)
            path.chmod(0o600)
        return directory

    def run_author(self, directory, raw=None, **kw):
        api = self.api()
        transport = api.FakeAuthorTransport(
            response(fixture_sources()[0]) if raw is None else raw
        )
        validator = FixtureValidator()
        receipt = api.author_offline(
            directory, transport=transport, validator=validator, unit_fixture=True, **kw
        )
        return receipt, transport, validator

    def test_actual_prompt_contains_version_bound_guide_and_fresh_call_contract(self):
        directory = self.setup_run()
        receipt, transport, _ = self.run_author(directory)
        instructions, prompt = transport.calls[0]
        self.assertIn(
            (ROOT / "chaos/prompts/next-use-author.txt").read_text(), instructions
        )
        self.assertIn(
            (ROOT / "chaos/prompts/next-use-mechanics.txt").read_text(), instructions
        )
        for term in (
            "LEGAL",
            "SOURCE",
            "MEASURED",
            "UNKNOWN",
            "6b7bd822c82d770bafa10af6e751cbf987231c6b",
            "do not persist",
            "not available in on_action",
            "not typical",
        ):
            self.assertIn(term, instructions)
        self.assertLessEqual(
            len((instructions + prompt).encode()), self.api().MAX_PROMPT_BYTES
        )
        self.assertEqual(
            receipt["prompt_sha256"],
            hashlib.sha256(
                (directory / "next_use-author-prompt.json").read_bytes()
            ).hexdigest(),
        )
        self.assertEqual(receipt["mode"], "offline_handwritten_fixture")
        self.assertEqual(receipt["validation"], "unit_fixture_not_native")
        self.assertEqual(receipt["native_admission"], "unverified")
        self.assertIn("guide_sha256", receipt)
        self.assertIn("capability_sha256", receipt)
        self.assertEqual(receipt["prompt_version"], "next-use-offline-author-v1")
        self.assertIn(
            "public_context.summary.observed.sanity and .insight", instructions
        )
        self.assertIn("must not read c.sanity or c.insight", instructions)
        observed = json.loads(prompt)["public_context"]["summary"]["observed"]
        self.assertEqual((observed["sanity"], observed["insight"]), (60, 0))

    def test_handwritten_examples_reach_bounded_private_free_prompt(self):
        calls = []
        for secret in ("PRIVATE-state-fate-7", "PRIVATE-map-target-3"):
            directory = self.setup_run(hidden=secret)
            receipt, transport, _ = self.run_author(directory)
            instructions, prompt = transport.calls[0]
            for label, source in HANDWRITTEN_EXAMPLES:
                self.assertIn(f"{label}\n```lua\n{source}```", instructions)
                self.assertNotIn(source, prompt)  # Instructions, not public history.
            assembled = instructions + prompt
            self.assertLessEqual(len(assembled.encode()), self.api().MAX_PROMPT_BYTES)
            self.assertEqual(receipt["prompt_bytes"], len(assembled.encode()))
            self.assertEqual(
                receipt["contract_sha256"],
                hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
            )
            for forbidden in (
                secret,
                str(directory),
                "history_checkpoint",
                "level_dnum",
                '"identity"',
                '"run"',
                '"move"',
            ):
                self.assertNotIn(forbidden, assembled)
            saved = json.loads((directory / "next_use-author-prompt.json").read_bytes())
            self.assertEqual(saved, {"instructions": instructions, "prompt": prompt})
            calls.append(transport.calls[0])
        self.assertEqual(calls[0], calls[1])

    def test_actions_vary_independently_of_prior_whispers(self):
        prompts = []
        for fact in ("sound_high", "sound_shrill"):
            _, transport, _ = self.run_author(self.setup_run(fact=fact))
            prompts.append(json.loads(transport.calls[0][1])["public_context"])
        self.assertNotEqual(prompts[0]["episodes"], prompts[1]["episodes"])
        self.assertEqual(prompts[0]["prior_whispers"], prompts[1]["prior_whispers"])

    def test_prior_expiry_varies_independently_of_actions_without_witness_upgrade(self):
        prompts = []
        for prior in ("admitted", "expired"):
            _, transport, _ = self.run_author(self.setup_run(prior=prior))
            prompts.append(json.loads(transport.calls[0][1])["public_context"])
        self.assertEqual(prompts[0]["episodes"], prompts[1]["episodes"])
        self.assertFalse(prompts[0]["prior_whispers"][0]["expiry_observed"])
        self.assertTrue(prompts[1]["prior_whispers"][0]["expiry_observed"])
        for prompt in prompts:
            self.assertNotIn("witnessed", json.dumps(prompt["prior_whispers"]))
            self.assertEqual(prompt["prior_whispers"][0]["accepted_seq"], 3)

    def test_private_extras_and_host_proof_do_not_reach_transport(self):
        payloads = []
        for secret in ("SECRET-fate-7", "SECRET-rng-map-m_id"):
            _, transport, _ = self.run_author(self.setup_run(hidden=secret))
            payload = transport.calls[0][1]
            for forbidden in (
                "SECRET",
                "directory",
                "identity",
                "level_dnum",
                '"run"',
                '"move"',
            ):
                self.assertNotIn(forbidden, payload)
            payloads.append(payload)
        self.assertEqual(payloads[0], payloads[1])

    def test_both_exact_nonconstant_fixture_sources_survive_publication(self):
        identities = []
        for source in fixture_sources():
            with self.subTest(source=source):
                directory = self.setup_run()
                raw = response(source)
                receipt, transport, validator = self.run_author(directory, raw)
                envelope_raw = (directory / "next_use-envelope.json").read_bytes()
                envelope = json.loads(envelope_raw)
                self.assertEqual(envelope["source"].encode(), source)
                self.assertEqual(
                    (directory / "next_use-author-response.json").read_bytes(), raw
                )
                self.assertEqual(validator.seen, [raw])
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(
                    receipt["source_sha256"], hashlib.sha256(source).hexdigest()
                )
                self.assertEqual(
                    receipt["envelope_sha256"], hashlib.sha256(envelope_raw).hexdigest()
                )
                self.assertEqual(envelope["operations"], ["W", "F"])
                self.assertEqual(envelope["cost"], 2)
                self.assertEqual(envelope["ttl"], 100)
                self.assertEqual(envelope["telegraph"], "next-use-v2-WF")
                self.assertEqual([o["root"] for o in envelope["origin_refs"]], [3, 6])
                self.assertEqual(
                    json.loads(
                        (directory / "next_use-author-receipt.json").read_bytes()
                    ),
                    receipt,
                )
                identities.append(receipt["source_sha256"])
        self.assertEqual(len(identities), 2)
        self.assertNotEqual(identities[0], identities[1])

    def test_malformed_extra_oversize_and_unrepaired_source_reject_once(self):
        good = response(fixture_sources()[0])
        extra = json.loads(good)
        extra["cost"] = 0
        cases = [
            b"not json",
            b"```json\n" + good + b"```",
            json.dumps(extra).encode(),
            b"x" * 8193,
            response(b"x" * 4097),
            response(b"x\0y"),
            b'{"next_use_author_v":2,"next_use_author_v":2,"abstain":true}',
            response(b"```lua\n" + fixture_sources()[0] + b"```"),
            response(
                b'return {on_action=function(c) return {next_use_intent_v=2,op="teleport",state=8,extra=1} end}'
            ),
            response(b"while true do end"),
        ]
        for raw in cases:
            with self.subTest(raw=raw[:50]):
                directory = self.setup_run()
                api = self.api()
                transport = api.FakeAuthorTransport(raw)
                with self.assertRaises(ValueError):
                    api.author_offline(
                        directory,
                        transport=transport,
                        validator=FixtureValidator(),
                        unit_fixture=True,
                    )
                self.assertEqual(len(transport.calls), 1)
                self.assertFalse((directory / "next_use-envelope.json").exists())
                receipt = json.loads(
                    (directory / "next_use-author-receipt.json").read_bytes()
                )
                self.assertEqual(receipt["status"], "rejected_not_admitted")
                self.assertIn(receipt["error_type"], ("ValueError", "JSONDecodeError"))
                self.assertEqual(
                    receipt["response_sha256"], hashlib.sha256(raw).hexdigest()
                )
                self.assertIsNone(receipt["envelope_sha256"])
                before = {p.name: p.read_bytes() for p in directory.glob("next_use-*")}
                if len(raw) <= 8192:
                    self.assertEqual(
                        (directory / "next_use-author-response.json").read_bytes(), raw
                    )
                with self.assertRaises((ValueError, FileExistsError)):
                    api.author_offline(
                        directory,
                        transport=transport,
                        validator=FixtureValidator(),
                        unit_fixture=True,
                    )
                self.assertEqual(len(transport.calls), 1)
                self.assertEqual(
                    {p.name: p.read_bytes() for p in directory.glob("next_use-*")},
                    before,
                )

    def test_abstention_is_retained_without_envelope(self):
        directory = self.setup_run()
        receipt, _, _ = self.run_author(
            directory, b'{"next_use_author_v":2,"abstain":true}'
        )
        self.assertEqual(receipt["status"], "abstained_not_admitted")
        self.assertIsNone(receipt["source_sha256"])
        self.assertFalse((directory / "next_use-envelope.json").exists())

    def test_production_requires_native_validator_before_transport(self):
        directory = self.setup_run()
        api = self.api()
        transport = api.FakeAuthorTransport(response(fixture_sources()[0]))
        for validator in (None, FixtureValidator()):
            with self.assertRaises(ValueError):
                api.author_offline(directory, transport=transport, validator=validator)
        self.assertEqual(transport.calls, [])
        self.assertFalse((directory / "next_use-envelope.json").exists())

    def test_arbitrary_or_live_transport_is_not_accepted(self):
        api = self.api()

        class LiveTransport:
            def generate(self, *args):
                raise AssertionError("must not be called")

        with self.assertRaises(ValueError):
            api.author_offline(
                self.setup_run(),
                transport=LiveTransport(),
                validator=FixtureValidator(),
                unit_fixture=True,
            )

    def test_invalid_or_stale_schedule_does_not_call_transport(self):
        for change in (
            "root",
            "unsupported",
            "extra",
            "duplicate",
            "too_many",
            "oversize",
            "partial",
        ):
            directory = self.setup_run()
            path = directory / "next_use-schedule.jsonl"
            rows = [json.loads(line) for line in path.read_bytes().splitlines()]
            if change == "root":
                for row in rows:
                    row.update(
                        root=row["root"] + 100,
                        notice_seq=row["notice_seq"] + 100,
                        end_seq=row["end_seq"] + 100,
                    )
            elif change == "unsupported":
                rows[0]["family"] = "X"
            elif change == "extra":
                rows[0]["cost"] = 0
            elif change == "duplicate":
                rows[1] = copy.deepcopy(rows[0])
            elif change == "too_many":
                rows = [
                    dict(
                        rows[0], root=3 * n + 3, notice_seq=3 * n + 4, end_seq=3 * n + 5
                    )
                    for n in range(33)
                ]
            raw = wire(*rows)
            path.write_bytes(
                b"x" * 16385
                if change == "oversize"
                else raw[:-1]
                if change == "partial"
                else raw
            )
            api = self.api()
            transport = api.FakeAuthorTransport(response(fixture_sources()[0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                api.author_offline(
                    directory,
                    transport=transport,
                    validator=FixtureValidator(),
                    unit_fixture=True,
                )
            self.assertEqual(transport.calls, [])

    def test_history_changed_during_fake_transport_rejects_publication(self):
        directory = self.setup_run()
        api = self.api()
        original = api.FakeAuthorTransport.generate

        def changed(transport, instructions, prompt):
            result = original(transport, instructions, prompt)
            path = directory / "events.jsonl"
            path.write_bytes(path.read_bytes().replace(b"SECRET", b"PUBLIC"))
            return result

        with patch.object(api.FakeAuthorTransport, "generate", changed):
            with self.assertRaisesRegex(ValueError, "history|prefix"):
                self.run_author(directory)
        self.assertFalse((directory / "next_use-envelope.json").exists())
        receipt = json.loads((directory / "next_use-author-receipt.json").read_bytes())
        self.assertEqual(receipt["status"], "rejected_not_admitted")

    def test_existing_envelope_or_partial_evidence_is_never_clobbered(self):
        for name in (
            "next_use-envelope.json",
            "next_use-author-prompt.json",
            "next_use-author-response.json",
            "next_use-author-receipt.json",
        ):
            directory = self.setup_run()
            path = directory / name
            path.write_bytes(b"KEEP EXACT")
            path.chmod(0o600)
            api = self.api()
            transport = api.FakeAuthorTransport(response(fixture_sources()[0]))
            with (
                self.subTest(name=name),
                self.assertRaises((ValueError, FileExistsError)),
            ):
                api.author_offline(
                    directory,
                    transport=transport,
                    validator=FixtureValidator(),
                    unit_fixture=True,
                )
            self.assertEqual(path.read_bytes(), b"KEEP EXACT")
            self.assertEqual(transport.calls, [])

    def test_prompt_cap_rejects_before_transport(self):
        api = self.api()
        transport = api.FakeAuthorTransport(response(fixture_sources()[0]))
        with patch.object(api, "MAX_PROMPT_BYTES", 10), self.assertRaises(ValueError):
            api.author_offline(
                self.setup_run(),
                transport=transport,
                validator=FixtureValidator(),
                unit_fixture=True,
            )
        self.assertEqual(transport.calls, [])

    def test_source_manifest_binds_every_guide_reference(self):
        api = self.api()
        manifest = json.loads(
            (ROOT / "chaos/prompts/next-use-mechanics-sources.json").read_bytes()
        )
        self.assertEqual(
            manifest["revision"], "6b7bd822c82d770bafa10af6e751cbf987231c6b"
        )
        for name, digest in manifest["files"].items():
            self.assertEqual(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest
            )
        self.assertIn("src/attrib.c", manifest["files"])
        self.assertIn("src/chaos_next_use_runtime.c", manifest["files"])
        self.assertIn("src/chaos_next_use_safe.c", manifest["files"])
        self.assertIn(
            "Production currently supplies both counts as zero",
            (ROOT / "chaos/prompts/next-use-mechanics.txt").read_text(),
        )
        with (
            patch.object(api, "SOURCE_REVISION", "0" * 40),
            self.assertRaises(ValueError),
        ):
            self.run_author(self.setup_run())

    def chronological_run(self, families, pending=None):
        directory = self.setup_run()
        rows = [enabled(), session(2)]
        schedules = []
        for family in families:
            operation, fact = {
                "W": ("whistling", "sound_high"),
                "F": ("fountain_drink", "water_refreshed"),
            }[family]
            origin = action(rows, operation, fact)
            schedules.append(
                dict(
                    next_use_schedule_v=1,
                    family=family,
                    move=10,
                    level_dnum=0,
                    level_dlevel=1,
                    root=origin["root_seq"],
                    notice_seq=origin["notice_seq"],
                    end_seq=origin["end_seq"],
                )
            )
        if pending:
            operation, fact = {
                "W": ("whistling", "sound_high"),
                "F": ("fountain_drink", "water_refreshed"),
            }[pending]
            action(rows, operation, fact, terminal=None)
        (directory / "events.jsonl").write_bytes(wire(*rows))
        (directory / "next_use-schedule.jsonl").write_bytes(wire(*schedules))
        return directory

    def test_schedule_chronology_is_not_canonical_envelope_order(self):
        for families in (
            ("W", "F"),
            ("F", "W"),
            ("W", "W"),
            ("F", "F", "F"),
            ("F", "W", "F", "W"),
        ):
            with self.subTest(families=families):
                directory = self.chronological_run(families)
                self.run_author(directory)
                envelope = json.loads(
                    (directory / "next_use-envelope.json").read_bytes()
                )
                expected = [f for f in ("W", "F") if f in families]
                self.assertEqual(envelope["operations"], expected)
                latest = {family: 3 + 3 * i for i, family in enumerate(families)}
                self.assertEqual(
                    [r["root"] for r in envelope["origin_refs"]],
                    [latest[f] for f in expected],
                )
                self.assertEqual((envelope["at"], envelope["id"]), (2, 1))

    def test_selected_completion_is_never_retimed_for_safe_or_id(self):
        for field in ("safe", "last_id"):
            with self.subTest(field=field):
                directory = self.chronological_run(("W", "F"))
                path = directory / "events.jsonl"
                rows = [json.loads(line) for line in path.read_bytes().splitlines()]
                rows.append(event(len(rows) + 1, **{field: rows[-1][field] + 1}))
                path.write_bytes(wire(*rows))
                transport = self.api().FakeAuthorTransport(
                    response(fixture_sources()[0])
                )
                with patch.object(
                    self.api(), "_instructions", return_value=("fixture", {})
                ):
                    with self.assertRaisesRegex(ValueError, "eligible|completion"):
                        self.api().author_offline(
                            directory,
                            transport=transport,
                            validator=FixtureValidator(),
                            unit_fixture=True,
                        )
                self.assertEqual(transport.calls, [])
                self.assertFalse((directory / "next_use-envelope.json").exists())

    def test_pending_newer_notice_suppresses_only_its_family(self):
        directory = self.chronological_run(("W", "F"), pending="W")
        self.run_author(directory)
        envelope = json.loads((directory / "next_use-envelope.json").read_bytes())
        self.assertEqual(envelope["operations"], ["F"])
        self.assertEqual(envelope["origin_refs"][0]["root"], 6)

    def test_append_between_final_snapshot_and_reader_is_rejected(self):
        directory = self.setup_run()
        api = self.api()
        original = api.snapshot_history
        calls = []

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(None)
            if len(calls) == 2:
                with (directory / "events.jsonl").open("ab") as stream:
                    stream.write(wire(event(11, turn=21, sanity=60, budget=6)))
            return result

        with patch.object(api, "snapshot_history", changed):
            with self.assertRaisesRegex(ValueError, "history"):
                self.run_author(directory)
        self.assertFalse((directory / "next_use-envelope.json").exists())
        receipt = json.loads((directory / "next_use-author-receipt.json").read_bytes())
        self.assertEqual(receipt["status"], "rejected_not_admitted")

    def test_schedule_replacement_during_transport_is_rejected(self):
        directory = self.setup_run()
        api = self.api()
        original = api.FakeAuthorTransport.generate

        def changed(transport, *args):
            raw = original(transport, *args)
            path = directory / "next_use-schedule.jsonl"
            replacement = directory / "replacement"
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            replacement.replace(path)
            return raw

        with patch.object(api.FakeAuthorTransport, "generate", changed):
            with self.assertRaisesRegex(ValueError, "replaced"):
                self.run_author(directory)
        self.assertFalse((directory / "next_use-envelope.json").exists())
        receipt = json.loads((directory / "next_use-author-receipt.json").read_bytes())
        self.assertEqual(receipt["status"], "rejected_not_admitted")

    def test_racing_envelope_publication_is_never_clobbered(self):
        directory = self.setup_run()
        api = self.api()
        original = api.FakeAuthorTransport.generate

        def changed(transport, *args):
            raw = original(transport, *args)
            path = directory / "next_use-envelope.json"
            path.write_bytes(b"KEEP EXACT")
            path.chmod(0o600)
            return raw

        with patch.object(api.FakeAuthorTransport, "generate", changed):
            with self.assertRaises(FileExistsError):
                self.run_author(directory)
        self.assertEqual(
            (directory / "next_use-envelope.json").read_bytes(), b"KEEP EXACT"
        )
        receipt = json.loads((directory / "next_use-author-receipt.json").read_bytes())
        self.assertEqual(receipt["status"], "publication_uncertain")
        self.assertEqual(receipt["native_admission"], "unverified")
        self.assertEqual(len(receipt["attempted_envelope_sha256"]), 64)
        self.assertNotEqual(
            receipt["attempted_envelope_sha256"],
            hashlib.sha256(b"KEEP EXACT").hexdigest(),
        )
        self.assertIsNone(receipt["envelope_sha256"])

    def test_post_publication_failures_record_uncertainty_without_erasing(self):
        for failure in ("post_link_fsync", "readback"):
            with self.subTest(failure=failure):
                directory = self.setup_run()
                api = self.api()
                target = directory / "next_use-envelope.json"
                real_sync = api.store.os.fsync
                real_read = api.store._read
                fired = []

                def sync(fd):
                    if failure == "post_link_fsync" and target.exists() and not fired:
                        fired.append(target.read_bytes())
                        raise OSError("injected post-link durability failure")
                    return real_sync(fd)

                def read(fd, name, maximum):
                    if failure == "readback" and name == target.name and not fired:
                        fired.append(target.read_bytes())
                        raise OSError("injected published-envelope readback failure")
                    return real_read(fd, name, maximum)

                with (
                    patch.object(api.store.os, "fsync", sync),
                    patch.object(api.store, "_read", read),
                ):
                    with self.assertRaises(OSError):
                        self.run_author(directory)
                self.assertEqual(len(fired), 1)
                self.assertEqual(target.read_bytes(), fired[0])
                receipt = json.loads(
                    (directory / "next_use-author-receipt.json").read_bytes()
                )
                self.assertEqual(receipt["status"], "publication_uncertain")
                self.assertEqual(receipt["native_admission"], "unverified")
                self.assertEqual(
                    receipt["attempted_envelope_sha256"],
                    hashlib.sha256(fired[0]).hexdigest(),
                )
                self.assertIsNone(receipt["envelope_sha256"])
                with self.assertRaisesRegex(ValueError, "no retry"):
                    self.run_author(directory)
                self.assertEqual(target.read_bytes(), fired[0])

    def test_fake_transport_error_has_a_final_receipt_and_no_retry(self):
        for error in (RuntimeError("fixture failure"), OSError("fixture I/O failure")):
            directory = self.setup_run()
            api = self.api()
            transport = api.FakeAuthorTransport(response(fixture_sources()[0]))
            with patch.object(
                api.FakeAuthorTransport, "generate", side_effect=error
            ) as generate:
                with self.assertRaises(type(error)):
                    api.author_offline(
                        directory,
                        transport=transport,
                        validator=FixtureValidator(),
                        unit_fixture=True,
                    )
                receipt = json.loads(
                    (directory / "next_use-author-receipt.json").read_bytes()
                )
                self.assertEqual(receipt["status"], "rejected_not_admitted")
                self.assertEqual(receipt["error_type"], type(error).__name__)
                self.assertFalse((directory / "next_use-envelope.json").exists())
                with self.assertRaisesRegex(ValueError, "no retry"):
                    api.author_offline(
                        directory,
                        transport=transport,
                        validator=FixtureValidator(),
                        unit_fixture=True,
                    )
                generate.assert_called_once()

    def test_only_current_completion_contributes_capabilities(self):
        for field in ("safe", "last_id"):
            directory = self.chronological_run(("W", "F"))
            path = directory / "events.jsonl"
            rows = [json.loads(line) for line in path.read_bytes().splitlines()]
            for row in rows[5:]:
                row[field] += 1
            path.write_bytes(wire(*rows))
            self.run_author(directory)
            envelope = json.loads((directory / "next_use-envelope.json").read_bytes())
            self.assertEqual(envelope["operations"], ["F"])
            self.assertEqual(envelope["at"], rows[-1]["safe"] + 1)
            self.assertEqual(envelope["id"], rows[-1]["last_id"] + 1)

    def test_pending_only_family_cannot_reuse_its_previous_origin(self):
        directory = self.chronological_run(("W",), pending="W")
        api = self.api()
        transport = api.FakeAuthorTransport(response(fixture_sources()[0]))
        with self.assertRaisesRegex(ValueError, "eligible"):
            api.author_offline(
                directory,
                transport=transport,
                validator=FixtureValidator(),
                unit_fixture=True,
            )
        self.assertEqual(transport.calls, [])

    def test_missing_native_library_is_not_a_python_parser_fallback(self):
        with self.assertRaises((ValueError, OSError)):
            self.api().NativeAuthorValidator(Path("/does-not-exist/author.so"))
