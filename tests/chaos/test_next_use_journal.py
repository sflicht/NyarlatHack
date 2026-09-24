"""Production journal through on_safe -> native drinkfountain, no shadow witness."""

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_next_use_fountain as native
from chaos.next_use_envelope import engine_run_hex, publish_envelope

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native.NextUseFountainTests.setUpClass()
        cls.build = native.NextUseFountainTests.root
        cls.exe = cls.build / "journal-native"
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/next_use_journal_native.c"),
                *map(str, native.NextUseFountainTests.objects),
                "-Wl,--wrap=write",
                "-Wl,--wrap=fsync",
                "-Wl,--wrap=close",
                "-lncursesw",
                "-ltinfo",
                "-lm",
                *subprocess.check_output(
                    ["pkg-config", "--libs", "lua5.4"], text=True
                ).split(),
                "-o",
                str(cls.exe),
            ],
            check=True,
            timeout=45,
        )

    @classmethod
    def tearDownClass(cls):
        # Only rebuildable files made by this suite, never receipts/source/logs.
        for p in cls.build.iterdir():
            if p.suffix == ".o" or p.name in ("fountain", "journal-native"):
                p.unlink()

    def test_driver_uses_preselected_seed_without_search(self):
        driver = (ROOT / "tests/chaos/next_use_journal_native.c").read_text()
        self.assertNotIn("find_seed(", driver)
        self.assertIn("srandom(123u)", driver)

    def test_program_expiry_has_readable_terminal_evidence(self):
        from chaos.next_use_journal import read_journal

        folder, row = self.run_native(mode="expire")
        trace = read_journal(folder / "next_use-journal.jsonl")
        self.assertEqual(trace["status"], "structurally_complete")
        self.assertEqual((row["incomplete"], row["cursor"]), (0, 1))
        transition = trace["records"][1]["data"]
        self.assertEqual(transition["callback_ordinal"], 0)
        self.assertEqual(transition["private_records"][-1]["data"]["reason"], 5)
        self.assertEqual(
            transition["at_move"],
            trace["records"][0]["data"]["snapshot"]["program_expiry"],
        )

    def run_native(self, fault=None, folder=None, escaped=False, mode=None):
        folder = folder or Path(tempfile.mkdtemp(prefix="nyarl-journal-run-"))
        if not (folder / "next_use-envelope.json").exists():
            publish_envelope(
                folder, native.ROW, dict(native.HOST, run=engine_run_hex(folder))
            )
        if escaped:
            p = folder / "next_use-envelope.json"
            e = json.loads(p.read_text())
            e["source"] += '\n-- bytes: " \\ café\t\r\n'
            e["source_sha256"] = hashlib.sha256(e["source"].encode()).hexdigest()
            p.write_text(
                json.dumps(e, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            )
        env = dict(os.environ, TERM="xterm", COLUMNS="80", LINES="24")
        env.pop("JOURNAL_TEST_FAULT", None)
        env.pop("JOURNAL_TEST_MODE", None)
        if mode:
            env["JOURNAL_TEST_MODE"] = mode
        if fault:
            env["JOURNAL_TEST_FAULT"] = fault
        result = subprocess.run(
            [str(self.exe), str(folder)],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        (folder / "native.log").write_text(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = json.loads((folder / "result.json").read_text())
        self.assertEqual(
            (row["admitted"], row["rejected"], row["spent"], row["hunger_delta"]),
            (0, 1, 0, 0)
            if mode == "deadline-late"
            else (1, 0, 1, 0 if mode == "expire" else 4),
        )
        print("JOURNAL_ARTIFACT=" + str(folder) + " " + json.dumps(row), flush=True)
        return folder, row

    @staticmethod
    def rehashed(path, rows):
        """Deliberate value corruption, not an authentic native capture."""
        prev, encoded = "0" * 64, b""
        for row in rows:
            row["payload"]["prev"] = prev
            payload = json.dumps(row["payload"], separators=(",", ":")).encode()
            prev = hashlib.sha256(payload).hexdigest()
            encoded += (
                b'{"payload":' + payload + b',"sha256":"' + prev.encode() + b'"}\n'
            )
        path.write_bytes(encoded)
        return path

    def test_native_origin_deadline_is_inclusive(self):
        from chaos.next_use_journal import read_journal

        folder, row = self.run_native(mode="deadline")
        envelope = json.loads((folder / "next_use-envelope.json").read_text())
        self.assertEqual(envelope["origin_refs"][0]["move"], 40)
        self.assertEqual(envelope["at"], 7)
        trace = read_journal(folder / "next_use-journal.jsonl")
        snapshot = trace["records"][0]["data"]["snapshot"]
        self.assertEqual(
            (snapshot["admission_move"], snapshot["program_expiry"]), (140, 240)
        )
        self.assertEqual(
            bytes.fromhex(snapshot["source_hex"]), envelope["source"].encode()
        )
        self.assertEqual(trace["status"], "structurally_complete")
        self.assertEqual(row["cursor"], 2)
        effect = trace["records"][-2]["data"]
        self.assertEqual((effect["at_move"], effect["fountain_outcome"]), (140, 6))
        # Engine consumes its bound copy, not the driver's original token.
        self.assertEqual(effect["expected_token"]["consumed"], 1)

    def test_native_origin_deadline_plus_one_rejects_without_journal(self):
        folder, row = self.run_native(mode="deadline-late")
        # Driver also asserts no telegraph, no installed snapshot, no debit;
        # it does not call fountain effects after this production rejection.
        self.assertEqual((row["cursor"], row["consumed"]), (0, 0))
        self.assertFalse((folder / "next_use-journal.jsonl").exists())

    def test_rehashed_f_trace_cannot_invent_public_w_witness(self):
        from chaos.next_use_journal import read_journal, JournalError

        folder, _ = self.run_native()
        rows = [
            json.loads(line)
            for line in (folder / "next_use-journal.jsonl").read_bytes().splitlines()
        ]
        self.assertEqual(rows[0]["payload"]["data"]["snapshot"]["slot_w"], 0)
        terminal = rows[-2]["payload"]["data"]
        terminal["public_count"] = 1
        terminal["public_records"] = [
            dict(
                next_use_public_v=2,
                family=1,
                phase=1,
                root=111,
                notice_seq=112,
                end_seq=113,
            )
        ]
        with self.assertRaises(JournalError):
            read_journal(self.rehashed(folder / "invented-public.jsonl", rows))

    def test_callback_age_exact_boundaries_without_clamping(self):
        from chaos.next_use_journal import read_journal, JournalError

        folder, _ = self.run_native()
        rows = [
            json.loads(line)
            for line in (folder / "next_use-journal.jsonl").read_bytes().splitlines()
        ]
        snapshot = rows[0]["payload"]["data"]["snapshot"]
        for age in (0, 99, 100, 101, 1000, -1):
            with self.subTest(age=age):
                changed = copy.deepcopy(rows[:2])
                t = changed[1]["payload"]["data"]
                t["at_move"] = snapshot["admission_move"] + age
                r = t["private_records"][0]
                r["at_move"] = t["at_move"]
                # Independent adversarial digest: reproduce the OLD clamp for
                # invalid values, exact valid age otherwise. Rehash whole trace.
                context = dict(
                    age=min(100, max(0, age)),
                    fountain_count=snapshot["fountain_count"],
                    next_use_context_v=2,
                    own_witnessed="none",
                    source_sha256=snapshot["source_sha256"],
                    state=0,
                    trigger="F",
                    variant=snapshot["variant"],
                    whistle_count=snapshot["whistle_count"],
                )
                r["data"]["context_sha256"] = hashlib.sha256(
                    json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                path = self.rehashed(folder / f"age-{age}.jsonl", changed)
                if 0 <= age <= 99:
                    self.assertEqual(read_journal(path)["status"], "incomplete")
                else:
                    with self.assertRaises(JournalError):
                        read_journal(path)

    def w_value_component(self):
        """Source-derived W values, NOT physical W evidence or native replay.

        Shapes come from a real F capture; W values follow runtime.c
        append_effect/on_manifestation and the capture wrappers/enums.
        """
        folder, _ = self.run_native()
        rows = [
            json.loads(line)["payload"]["data"]
            for line in (folder / "next_use-journal.jsonl").read_bytes().splitlines()
        ]
        s, t = copy.deepcopy(rows[0]["snapshot"]), copy.deepcopy(rows[1])
        s.update(slot_w=1, slot_f=0, origin_w=10, origin_f=0)
        p = t["post"]
        p.update(
            callback_w=1,
            callback_f=0,
            f_inflight=0,
            f_root=0,
            armed_m_id=77,
            expected_manifest_m_id=77,
            armed_root=20,
            activation_monstermoves=40,
            attention_claimed=1,
            witnessed=0,
            origin_w_live=1,
            origin_f_live=0,
        )
        prior = dict(p, state=0, w_runtime=1)
        t.update(
            operation=5,
            family=0,
            root=111,
            manifest_root=111,
            notice_root=111,
            notice_seq=112,
            witness_notice_seq=112,
            end_seq=113,
            m_id=77,
            expected_result=1,
            published=1,
            pre_public=1,
            manifestation_delivered=1,
            displaced=1,
            slot_w=2,
            slot_f=0,
            w_runtime=1,
            seq=5,
            state=0,
            token_present=0,
            expected_token=dict(root=0, active=0, remap=0, consumed=0),
            private_count=1,
            public_count=1,
        )
        r = copy.deepcopy(rows[2]["private_records"][0])
        r.update(
            seq=5,
            data=dict(
                family=1, outcome=3, root=111, activation_monstermoves=40, m_id=77
            ),
        )
        t["private_records"] = [r]
        t["public_records"] = [
            dict(
                next_use_public_v=2,
                family=1,
                phase=1,
                root=111,
                notice_seq=112,
                end_seq=113,
            )
        ]
        p["witnessed"] = 1
        return s, t, prior

    def test_w_public_binding_source_derived_component(self):
        from chaos.next_use_journal import _transition, JournalError

        s, t, prior = self.w_value_component()
        _transition(t, s, 4, prior)
        edits = [
            (("operation",), 6),
            (("published",), 0),
            (("pre_public",), 0),
            (("manifestation_delivered",), 0),
            (("displaced",), 0),
            (("invalid",), 1),
            (("expected_result",), 0),
            (("m_id",), 78),
            (("root",), 110),
            (("manifest_root",), 110),
            (("notice_root",), 110),
            (("notice_seq",), 114),
            (("witness_notice_seq",), 114),
            (("end_seq",), 114),
            (("post", "witnessed"), 0),
            (("post", "armed_m_id"), 78),
            (("post", "expected_manifest_m_id"), 78),
            (("post", "manifest_success"), 1),
            (("post", "expected_manifest_root"), 111),
            (("post", "expected_notice_seq"), 112),
            (("post", "expected_end_seq"), 113),
            (("public_records", 0, "root"), 110),
            (("public_records", 0, "notice_seq"), 111),
            (("public_records", 0, "end_seq"), 114),
            (("private_records", 0, "data", "outcome"), 1),
            (("private_records", 0, "data", "root"), 110),
            (("private_records", 0, "data", "m_id"), 78),
            (("private_records", 0, "data", "activation_monstermoves"), 41),
        ]
        for route, value in edits:
            with self.subTest(route=route):
                changed = copy.deepcopy(t)
                target = changed
                for key in route[:-1]:
                    target = target[key]
                target[route[-1]] = value
                with self.assertRaises(JournalError):
                    _transition(changed, s, 4, prior)
        denied = copy.deepcopy(t)
        denied.update(
            published=0,
            public_count=0,
            public_records=[],
            private_count=0,
            private_records=[],
            seq=4,
        )
        denied["post"]["witnessed"] = 0
        _transition(denied, s, 4, prior)  # delivered/displaced != published
        no_op = copy.deepcopy(denied)
        no_op["post"]["witnessed"] = 1
        _transition(no_op, s, 4, dict(prior, witnessed=1))
        for key in ("public", "private"):
            missing = copy.deepcopy(t)
            missing[key + "_records"] = []
            missing[key + "_count"] = 0
            if key == "private":
                missing["seq"] = 4
            with self.subTest(missing=key), self.assertRaises(JournalError):
                _transition(missing, s, 4, prior)

    def test_w_zero_root_termination_source_derived_component(self):
        from chaos.next_use_journal import _transition, JournalError

        s, base, prior = self.w_value_component()
        # runtime_end_w_impl: reasons 1..5 have NULL current root, outcome
        # ENDED_AFTER_WITNESS(4) / ENDED_NO_WITNESS(5); reason6 stays rooted.
        for witnessed in (0, 1):
            for reason, runtime_state in ((1, 2), (2, 4), (3, 3), (4, 3), (5, 3)):
                with self.subTest(witnessed=witnessed, reason=reason):
                    t = copy.deepcopy(base)
                    before = dict(prior, witnessed=witnessed)
                    t.update(
                        operation=13,
                        end_reason=reason,
                        root=0,
                        root_present=0,
                        public_count=0,
                        public_records=[],
                        w_runtime=runtime_state,
                    )
                    t["post"]["witnessed"] = witnessed
                    t["private_records"][0]["data"].update(
                        root=0, outcome=4 if witnessed else 5
                    )
                    _transition(t, s, 4, before)
                    for bad_outcome in (1, 2, 3, 6):
                        bad = copy.deepcopy(t)
                        bad["private_records"][0]["data"]["outcome"] = bad_outcome
                        with self.assertRaises(JournalError):
                            _transition(bad, s, 4, before)
                    for updates in (
                        dict(operation=5),
                        dict(end_reason=6),
                        dict(root_present=1),
                    ):
                        bad = copy.deepcopy(t)
                        bad.update(updates)
                        with self.assertRaises(JournalError):
                            _transition(bad, s, 4, before)

    def test_physical_fountain_writes_complete_typed_journal(self):
        folder, row = self.run_native(escaped=True)
        path = folder / "next_use-journal.jsonl"
        self.assertTrue(
            path.exists(), "production safe admission did not bind physical journal"
        )
        from chaos.next_use_journal import read_journal

        trace = read_journal(path)
        self.assertEqual(trace["status"], "structurally_complete")
        self.assertIsNone(trace["capture_acknowledged"])
        self.assertEqual(row["incomplete"], 0)
        self.assertEqual(row["cursor"], 2)
        header = trace["records"][0]["data"]
        envelope = json.loads((folder / "next_use-envelope.json").read_text())
        self.assertEqual(
            bytes.fromhex(header["snapshot"]["source_hex"]), envelope["source"].encode()
        )
        records = trace["records"][1:-1]
        self.assertEqual([r["data"]["operation"] for r in records], [1, 6])
        self.assertEqual(records[-1]["data"]["fountain_outcome"], 6)
        self.assertEqual(records[-1]["data"]["expected_token"]["consumed"], 1)

    def test_retry_partial_write_and_eintr(self):
        from chaos.next_use_journal import read_journal

        folder, row = self.run_native("short")
        self.assertEqual(row["cursor"], 2)
        self.assertEqual(
            read_journal(folder / "next_use-journal.jsonl")["status"],
            "structurally_complete",
        )

    def test_complete_bytes_do_not_prove_capture_acknowledgement(self):
        from chaos.next_use_journal import read_journal

        for fault in ("sync4-persistent", "close"):
            with self.subTest(fault=fault):
                folder, row = self.run_native(fault)
                self.assertEqual((row["incomplete"], row["cursor"]), (1, 1))
                # Final footer survived but fsync/close failed; marker cannot land.
                trace = read_journal(folder / "next_use-journal.jsonl")
                self.assertEqual(trace["status"], "structurally_complete")
                self.assertIsNone(trace["capture_acknowledged"])
                evidence = {
                    "sink_connected": 1,
                    "incomplete": row["incomplete"],
                    "transaction_open": 0,
                    "acknowledged_cursor": row["cursor"],
                }
                trace = read_journal(
                    folder / "next_use-journal.jsonl", capture_status=evidence
                )
                self.assertEqual(trace["capture_acknowledged"], False)
                self.assertEqual(trace["status"], "capture_failed")

    def test_success_requires_separately_observed_capture_status(self):
        from chaos.next_use_journal import read_journal, JournalError

        folder, row = self.run_native()
        evidence = {
            "sink_connected": 1,
            "incomplete": row["incomplete"],
            "transaction_open": 0,
            "acknowledged_cursor": row["cursor"],
        }
        trace = read_journal(folder / "next_use-journal.jsonl", capture_status=evidence)
        self.assertTrue(trace["capture_acknowledged"])
        self.assertEqual(trace["status"], "acknowledged_complete")
        evidence["acknowledged_cursor"] += 1
        with self.assertRaises(JournalError):
            read_journal(folder / "next_use-journal.jsonl", capture_status=evidence)

    def test_failures_do_not_ack_or_reject_admission(self):
        from chaos.next_use_journal import read_journal, JournalError

        for fault in ("sync1", "sync2", "sync3", "sync4", "write", "zero"):
            with self.subTest(fault=fault):
                folder, row = self.run_native(fault)
                self.assertEqual(row["incomplete"], 1)
                self.assertLess(row["cursor"], 2)
                try:
                    trace = read_journal(folder / "next_use-journal.jsonl")
                except JournalError:
                    continue
                self.assertEqual(trace["status"], "incomplete")

    def test_exclusive_reopen_preserves_existing_trace(self):
        folder, _ = self.run_native()
        path = folder / "next_use-journal.jsonl"
        before = path.read_bytes()
        _, row = self.run_native(folder=folder)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((row["incomplete"], row["cursor"]), (1, 0))

    def test_symlink_does_not_touch_target(self):
        folder = Path(tempfile.mkdtemp(prefix="nyarl-journal-run-"))
        target = folder / "untouched"
        target.write_bytes(b"keep")
        (folder / "next_use-journal.jsonl").symlink_to(target)
        _, row = self.run_native(folder=folder)
        self.assertEqual(target.read_bytes(), b"keep")
        self.assertEqual((row["incomplete"], row["cursor"]), (1, 0))

    def test_rehashed_semantic_corruptions(self):
        from chaos.next_use_journal import read_journal, JournalError

        folder, _ = self.run_native()
        original = (folder / "next_use-journal.jsonl").read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        edits = [
            ((0, "snapshot", "binding_sha256"), "0" * 64),
            ((0, "snapshot", "snapshot_v"), 3),
            ((0, "snapshot", "run_token"), 2**63),
            ((0, "snapshot", "extra"), 1),
            ((0, "private_records", 1, "data", "envelope_sha256"), "0" * 64),
            ((0, "private_records", 1, "data", "operation_count"), 2),
            ((0, "private_records", 1, "data", "origin_roots", 0), 9),
            ((1, "replay_input_v"), 0),
            ((1, "callback_ordinal"), 2),
            ((1, "private_count"), 2),
            ((1, "public_count"), 1),
            ((1, "cursor"), 2),
            ((1, "published"), 0.0),
            ((1, "operation"), 14),
            ((1, "m_id"), 2**32),
            ((1, "slot_w"), -1),
            ((1, "post", "new_field"), 0),
            ((1, "post", "f_inflight"), 2),
            ((1, "private_records", 0, "next_use_private_v"), 1),
            ((1, "private_records", 0, "program_id"), 2),
            ((1, "private_records", 0, "seq"), 4),
            ((1, "private_records", 0, "data", "context_sha256"), "0" * 64),
            ((1, "private_records", 0, "data", "intent_sha256"), "0" * 64),
            ((1, "expected_token", "root"), 11),
            ((2, "expected_token", "consumed"), 0),
            ((2, "private_records", 0, "data", "root"), 11),
            ((2, "private_records", 1, "data", "reason"), 8),
            ((2, "private_records", 1, "data", "slot_f"), 4),
            ((3, "terminal_seq"), 4),
        ]
        for route, value in edits:
            with self.subTest(route=route):
                changed = copy.deepcopy(rows)
                target = changed[route[0]]["payload"]["data"]
                for key in route[1:-1]:
                    target = target[key]
                target[route[-1]] = value
                prev, encoded = "0" * 64, b""
                for r in changed:
                    r["payload"]["prev"] = prev
                    # Rehash ALL records: failures must be semantic, not checksum.
                    payload = json.dumps(r["payload"], separators=(",", ":")).encode()
                    prev = hashlib.sha256(payload).hexdigest()
                    encoded += (
                        b'{"payload":'
                        + payload
                        + b',"sha256":"'
                        + prev.encode()
                        + b'"}\n'
                    )
                p = folder / "semantic.jsonl"
                p.write_bytes(encoded)
                with self.assertRaises(JournalError) as caught:
                    read_journal(p)
                self.assertNotIn(
                    str(caught.exception), ("payload digest", "chain digest")
                )

    def test_duplicate_keys_and_exact_payload_hash(self):
        from chaos.next_use_journal import read_journal, JournalError

        folder, _ = self.run_native()
        rows = [
            json.loads(line)
            for line in (folder / "next_use-journal.jsonl").read_bytes().splitlines()
        ]
        # Whitespace and key ordering are not JCS: hash the original payload bytes.
        payload = json.dumps(rows[0]["payload"], separators=(", ", ": ")).encode()

        def outer(payload):
            return (
                b'{"payload":'
                + payload
                + b',"sha256":"'
                + hashlib.sha256(payload).hexdigest().encode()
                + b'"}\n'
            )

        p = folder / "bytes.jsonl"
        p.write_bytes(outer(payload))
        self.assertEqual(read_journal(p)["status"], "incomplete")
        for bad in (
            payload.replace(b'"v": 1', b'"v": 1, "v": 1', 1),
            payload.replace(b'"snapshot_v": 4', b'"snapshot_v": 4, "snapshot_v": 4', 1),
            payload.replace(b'"phase": 3', b'"phase": NaN', 1),
        ):
            p.write_bytes(outer(bad))
            with self.assertRaises(JournalError):
                read_journal(p)

    def test_strict_reader_corruptions_and_incomplete_prefixes(self):
        from chaos.next_use_journal import (
            read_journal,
            JournalError,
            MAX_BYTES,
            MAX_LINE,
        )

        folder, _ = self.run_native()
        original = (folder / "next_use-journal.jsonl").read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        path = folder / "corrupt.jsonl"

        def verify(data):
            path.write_bytes(data)
            return read_journal(path)

        def encode(changed):
            prev = "0" * 64
            result = b""
            for r in changed:
                r["payload"]["prev"] = prev
                payload = json.dumps(r["payload"], separators=(",", ":")).encode()
                prev = hashlib.sha256(payload).hexdigest()
                r["sha256"] = prev
                result += json.dumps(r, separators=(",", ":")).encode() + b"\n"
            return result

        for data in (
            original[:-1],
            original[:-30],
            b"{}\n",
            b"x" * (MAX_LINE + 1),
            b"x" * (MAX_BYTES + 1),
            original + original,
            original.replace(b'"cursor":1', b'"cursor":9', 1),
        ):
            with self.subTest(data=data[:50]):
                with self.assertRaises(JournalError):
                    verify(data)
        for edit in ("cursor", "source", "field", "bool", "byte", "terminal"):
            changed = copy.deepcopy(rows)
            if edit == "cursor":
                changed[1]["payload"]["cursor"] = 8
            if edit == "source":
                changed[0]["payload"]["data"]["snapshot"]["source_hex"] = "61"
            if edit == "field":
                changed[1]["payload"]["data"]["unknown"] = 0
            if edit == "bool":
                changed[1]["payload"]["data"]["published"] = True
            if edit == "byte":
                changed[0]["payload"]["data"]["snapshot"]["source_hex"] = "61" * 4097
            if edit == "terminal":
                changed[2]["payload"]["data"]["post"]["termination_emitted"] = 0
            with self.subTest(edit=edit), self.assertRaises(JournalError):
                verify(encode(changed))
        self.assertEqual(
            verify(b"\n".join(original.splitlines()[:-1]) + b"\n")["status"],
            "incomplete",
        )
        self.assertEqual(
            verify(original.splitlines()[0] + b"\n")["status"], "incomplete"
        )
