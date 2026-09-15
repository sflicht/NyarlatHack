"""Synthetic native-shaped receipts on private real FS; not live game evidence."""

import copy
from functools import partial
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chaos.curio import compose_prompt
from chaos.curio_store import install_saved_source, store_candidate


def put(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def events(details):
    result = []
    spent = 0
    for seq, detail in enumerate(details, 1):
        if detail == "admitted":
            spent += 1
        result.append(
            dict(
                v=1,
                seq=seq,
                turn=1,
                safe=0,
                sanity=100,
                insight=0,
                budget=1 - spent,
                spent=spent,
                reserved=0,
                last_id=0,
                event="session" if detail in ("new", "restore") else "curio",
                phase="result",
                detail=detail,
            )
        )
    return b"".join(json.dumps(e).encode() + b"\n" for e in result)


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("chaos.curio_continuity")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundles = self.root / "bundles"
        self.journal = self.root / "journal"
        self.run_dir = self.root / "run"
        for p in (self.bundles, self.journal, self.run_dir):
            p.mkdir(mode=0o700)
        self.api.create_journal(self.journal)
        self.c = self.candidate(0)

    def candidate(self, n):
        c = store_candidate(
            self.bundles,
            json.dumps(
                dict(
                    lua_source=f"-- synthetic {n}",
                    continuity_note=f"proposal {n}; status=placed is only prose",
                )
            ),
        )
        self.api.register(self.journal, self.bundles, c.candidate_id)
        return c

    def bind(self):
        install_saved_source(
            self.run_dir, bundle_root=self.bundles, candidate_id=self.c.candidate_id
        )
        self.api.bind_run(self.journal, self.c.candidate_id, self.run_dir)

    def log(self, details, used=True):
        put(self.run_dir / "events.jsonl", events(details))
        if used:
            put(self.run_dir / "curio-used.lua", self.c.lua_source)

    def notes(self):
        return self.api.prior_notes(self.journal)

    def observe(self):
        self.api.observe(self.journal, self.c.candidate_id)

    def test_authored_installed_and_read_only(self):
        self.assertEqual(self.notes()[0]["status"], "authored")
        self.bind()
        with patch("os.fsync", side_effect=AssertionError("read wrote")):
            self.assertEqual(self.notes()[0]["status"], "installed")
        with self.assertRaises(TypeError):
            self.api.register(
                self.journal, self.bundles, self.c.candidate_id, status="placed"
            )

    def test_admission_placement_checkpoint_restart(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        with self.assertRaises(ValueError):
            self.notes()  # uncheckpointed suffix cannot feed a prompt
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "admitted")
        self.log(
            [
                "new",
                "pre_admitted",
                "admitted",
                "placement_unavailable",
                "placed",
                "applied requested=2 actual=1",
            ]
        )
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "placed")
        compose_prompt(dict(sanity=100, insight=0), prior_notes=self.notes())

    def test_rejected_after_pre_admission(self):
        self.bind()
        self.log(["new", "pre_admitted", "rejected"])
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "rejected")

    def test_expiry_prompt(self):
        self.bind()
        self.log(["new", "expired"], used=False)
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "expired")
        compose_prompt(dict(sanity=100, insight=0), prior_notes=self.notes())

    def test_bad_chains_fail_closed(self):
        self.bind()
        for chain in (
            ["new", "pre_admitted"],
            ["new", "placed"],
            ["new", "admitted"],
            ["new", "rejected", "admitted"],
            ["new", "pre_admitted", "admitted", "placed", "expired"],
            ["new", "pre_admitted", "admitted", "applied requested=1 actual=1"],
            ["new", "unknown"],
            ["restore"],
        ):
            with self.subTest(chain=chain):
                self.log(chain)
                with self.assertRaises(ValueError):
                    self.observe()

    def test_latest_six_does_not_hide_old_evidence(self):
        ids = [self.c.candidate_id] + [
            self.candidate(n).candidate_id for n in range(1, 8)
        ]
        self.assertEqual([n["candidate_id"] for n in self.notes()], ids[-6:])
        put(self.bundles / ids[0] / "continuity-note.txt", b"tampered")
        with self.assertRaises(ValueError):
            self.notes()

    def test_duplicate_registration_and_wrong_run(self):
        with self.assertRaises(ValueError):
            self.api.register(self.journal, self.bundles, self.c.candidate_id)
        self.bind()
        with self.assertRaises(ValueError):
            self.api.bind_run(self.journal, self.c.candidate_id, self.run_dir)
        put(self.run_dir / "curio.lua", b"wrong")
        with self.assertRaises(ValueError):
            self.notes()

    def test_event_rewrite_truncate_replace_missing_partial(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()
        p = self.run_dir / "events.jsonl"
        good = p.read_bytes()
        for bad in (good[:-1], good.replace(b'"sanity": 100', b'"sanity": 99'), b""):
            put(p, bad)
            with self.assertRaises(ValueError):
                self.observe()
        put(p, good)
        p.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.notes()
        put(p, good)
        with self.assertRaises(ValueError):
            self.observe()

    def test_rollback_restore_even_with_unchanged_prefix(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()
        p = self.run_dir / "events.jsonl"
        e = json.loads(events(["restore"]))
        e.update(seq=4, turn=1, spent=0)
        put(p, p.read_bytes() + json.dumps(e).encode() + b"\n")
        with self.assertRaises(ValueError):
            self.observe()

    def test_missing_checkpoint_and_unknown_files(self):
        put(self.journal / "junk", b"x")
        with self.assertRaises(ValueError):
            self.notes()
        (self.journal / "junk").unlink()
        (self.journal / "000001.commit").unlink()
        with self.assertRaises((ValueError, OSError)):
            self.notes()

    def test_fsync_failure_retains_incomplete_evidence(self):
        c = self.candidate_unregistered()
        original = os.fsync
        calls = 0

        def fail_commit(fd):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise OSError("sync failed")
            return original(fd)

        with patch("os.fsync", side_effect=fail_commit):
            with self.assertRaises(OSError):
                self.api.register(self.journal, self.bundles, c.candidate_id)
        self.assertTrue((self.journal / "000002.json").exists())
        with self.assertRaises(ValueError):
            self.notes()

    def candidate_unregistered(self):
        # Precreate before fault injection is used in the dedicated test below.
        return store_candidate(
            self.bundles, json.dumps(dict(lua_source="-- other", continuity_note=""))
        )

    def test_late_admission_receipt_rejected(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        p = self.run_dir / "events.jsonl"
        lines = p.read_bytes().splitlines()
        e = json.loads(lines[-1])
        e["turn"] += 10
        lines[-1] = json.dumps(e).encode()
        put(p, b"\n".join(lines) + b"\n")
        with self.assertRaises(ValueError):
            self.observe()

    def test_nonblocking_lock_and_caps(self):
        from chaos.director import Mailbox

        with Mailbox(self.journal), self.assertRaises(ValueError):
            self.notes()
        c = self.candidate_unregistered()
        with patch.object(self.api, "MAX_RECORDS", 1), self.assertRaises(ValueError):
            self.api.register(self.journal, self.bundles, c.candidate_id)
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        with patch.object(self.api, "MAX_EVENTS", 2), self.assertRaises(ValueError):
            self.observe()

    def test_historical_checkpoint_cannot_omit_used_source(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()
        self.log(["new", "pre_admitted", "admitted", "placed"])
        self.observe()
        # Rehash the journal, but leave an internally impossible earlier proof.
        import hashlib

        previous = "0" * 64
        for i in range(1, 5):
            p = self.journal / f"{i:06d}.json"
            r = json.loads(p.read_bytes())
            r["previous"] = previous
            if i == 3:
                del r["proof"]["run"]["files"]["curio-used.lua"]
            raw = json.dumps(r).encode()
            previous = hashlib.sha256(raw).hexdigest()
            put(p, raw)
            put(self.journal / f"{i:06d}.commit", previous.encode())
        with self.assertRaises(ValueError):
            self.notes()

    def test_read_missing_lock_never_recreates(self):
        (self.journal / ".director.lock").unlink()
        with self.assertRaises(OSError):
            self.notes()
        self.assertFalse((self.journal / ".director.lock").exists())

    def fresh(self, label):
        """Independent private journal/run; reuse only the verified raw bundle."""
        self.journal = self.root / (label + "-journal")
        self.run_dir = self.root / (label + "-run")
        self.journal.mkdir(mode=0o700)
        self.run_dir.mkdir(mode=0o700)
        self.api.create_journal(self.journal)
        self.api.register(self.journal, self.bundles, self.c.candidate_id)

    def records(self):
        return [
            json.loads(p.read_bytes())
            for p in sorted(self.journal.glob("*.json"))
            if p.name != "journal.json"
        ]

    def rewrite(self, records):
        # Independent digest chain builder for meaningful host-schema mutations.
        # This is NOT a lifecycle oracle or a same-UID authenticity claim.
        previous = "0" * 64
        for i, record in enumerate(records, 1):
            r = copy.deepcopy(record)
            if "previous" in r:
                r["previous"] = previous
            raw = json.dumps(r).encode()
            previous = hashlib.sha256(raw).hexdigest()
            put(self.journal / f"{i:06d}.json", raw)
            put(self.journal / f"{i:06d}.commit", previous.encode())

    def test_journal_order_schema_and_pair_matrix(self):
        self.bind()
        original = self.records()
        cases = []
        for key, values in {
            "version": [True, 2, "1"],
            "seq": [True, 0, 3],
            "op": ["register", "observe", [], "unknown"],
            "candidate_id": ["A" * 64, "0" * 63, None],
            "bundle_root": [False, "../bundles", "/tmp/" + "x" * 2049],
            "run": [False, "../run", None],
        }.items():
            for value in values:
                changed = copy.deepcopy(original)
                changed[1][key] = value
                cases.append((f"{key}={value!r}", changed))
        for key in original[1]:
            changed = copy.deepcopy(original)
            del changed[1][key]
            cases.append(("missing " + key, changed))
        changed = copy.deepcopy(original)
        changed[1]["extra"] = "no"
        cases.append(("extra", changed))
        changed = copy.deepcopy(original)
        changed.reverse()
        cases.append(("reordered", changed))
        for label, changed in cases:
            with self.subTest(mutation=label):
                self.rewrite(changed)
                with self.assertRaises(ValueError):
                    self.notes()
        self.rewrite(original)
        # Independently hashed but incorrect predecessor.
        p = self.journal / "000002.json"
        r = json.loads(p.read_bytes())
        r["previous"] = "f" * 64
        raw = json.dumps(r).encode()
        put(p, raw)
        put(p.with_suffix(".commit"), hashlib.sha256(raw).hexdigest().encode())
        with self.assertRaises(ValueError):
            self.notes()
        self.rewrite(original)
        # Duplicate record pair, numeric gap, and duplicate JSON key.
        for label, target in [("duplicate", "000003"), ("gap", "000004")]:
            with self.subTest(mutation=label):
                for ext in ("json", "commit"):
                    shutil.copyfile(
                        self.journal / ("000002." + ext),
                        self.journal / (target + "." + ext),
                    )
                    (self.journal / (target + "." + ext)).chmod(0o600)
                with self.assertRaises(ValueError):
                    self.notes()
                for ext in ("json", "commit"):
                    (self.journal / (target + "." + ext)).unlink()
        raw = p.read_bytes().replace(b"{", b'{"seq": 2,', 1)
        put(p, raw)
        put(p.with_suffix(".commit"), hashlib.sha256(raw).hexdigest().encode())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.notes()
        self.rewrite(original)
        for name in ("000001.json", "000001.commit", "000002.json", "000002.commit"):
            with self.subTest(missing=name):
                path = self.journal / name
                raw = path.read_bytes()
                path.unlink()
                with self.assertRaises(ValueError):
                    self.notes()
                put(path, raw)
        put(self.journal / "000002.commit", b"0" * 64)
        with self.assertRaisesRegex(ValueError, "checkpoint"):
            self.notes()

    def test_proof_schema_mutations_in_old_and_latest_history(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()
        self.log(["new", "pre_admitted", "admitted", "placed"])
        self.observe()
        original = self.records()
        mutations = [
            ((), None),
            (("run",), None),
            (("run",), []),
            (("raw_sha256",), False),
            (("raw_sha256",), "f" * 64),
            (("run", "identity"), [True, 1]),
            (("run", "identity"), [1]),
            (("run", "identity"), [-1, 2]),
            (("run", "identity"), [0, 0]),
            (("run", "files"), []),
            (("run", "files"), {}),
        ]
        for prefix in [
            ("run", "event"),
            ("run", "files", "curio.lua"),
            ("run", "files", "curio-install.json"),
            ("run", "files", "curio-used.lua"),
        ]:
            mutations.extend([(prefix, {}), (prefix, False)])
            for key, values in {
                "identity": [[1], [True, 2], [0, 0]],
                "length": [True, -1, 1048577, "1", 0],
                "sha256": [False, "x" * 64, "0" * 64],
            }.items():
                mutations.extend((prefix + (key,), value) for value in values)
        for index in (2, 3):
            for path, value in mutations:
                with self.subTest(record=index + 1, path=path, value=value):
                    changed = copy.deepcopy(original)
                    if not path:
                        changed[index]["proof"] = value
                    else:
                        target = changed[index]["proof"]
                        for key in path[:-1]:
                            target = target[key]
                        target[path[-1]] = value
                    self.rewrite(changed)
                    with self.assertRaises(ValueError):
                        self.notes()
            for path in [(), ("run",), ("run", "event"), ("run", "files", "curio.lua")]:
                target = original[index]["proof"]
                for key in path:
                    target = target[key]
                for key in [*target, "extra"]:
                    with self.subTest(record=index + 1, schema_path=path, key=key):
                        changed = copy.deepcopy(original)
                        dest = changed[index]["proof"]
                        for part in path:
                            dest = dest[part]
                        if key == "extra":
                            dest[key] = 1
                        else:
                            del dest[key]
                        self.rewrite(changed)
                        with self.assertRaises(ValueError):
                            self.notes()
        self.rewrite(original)
        self.assertEqual(self.notes()[0]["status"], "placed")

    def test_checkpoint_prefix_rollback_rejects(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()
        self.log(["new", "pre_admitted", "admitted", "placed"])
        self.observe()
        records = self.records()
        records[-1]["proof"]["run"]["event"] = records[1]["proof"]["run"]["event"]
        self.rewrite(records)
        with self.assertRaises(ValueError):
            self.notes()

    def test_same_id_fully_rebuilt_raw_note_bundle_rejects(self):
        self.assertEqual(
            self.notes()[0]["continuity_note"],
            "proposal 0; status=placed is only prose",
        )
        old = self.bundles / self.c.candidate_id
        old.rename(self.root / "old-bundle")
        alternate = store_candidate(
            self.bundles,
            json.dumps(
                dict(
                    lua_source=self.c.lua_source.decode(),
                    continuity_note="alternate note",
                )
            ),
        )
        self.assertEqual(alternate.candidate_id, self.c.candidate_id)
        from chaos.curio_store import read_candidate

        self.assertEqual(
            read_candidate(self.bundles, self.c.candidate_id).continuity_note,
            "alternate note",
        )
        with self.assertRaisesRegex(ValueError, "conflicting raw/note"):
            self.notes()

    def test_snapshot_bytes_used_for_exact_source_validation(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        original = self.api.store._verify

        def raced_verify(*args):
            result = original(*args)
            put(self.run_dir / "curio-used.lua", b"-- other exact source")
            return result

        with patch.object(self.api.store, "_verify", side_effect=raced_verify):
            with self.assertRaises(ValueError):
                self.api._evidence(self.bundles, self.c.candidate_id, str(self.run_dir))
        # _evidence is exercised directly so a later read cannot mask a false
        # successful snapshot and publish an invalid checkpoint before rejecting.

    def test_malformed_event_schema_has_validation_errors(self):
        self.bind()
        for value in (None, [], {}, True):
            with self.subTest(event=value):
                e = json.loads(events(["new"]))
                if value is None:
                    del e["event"]
                else:
                    e["event"] = value
                put(self.run_dir / "events.jsonl", json.dumps(e).encode() + b"\n")
                with self.assertRaises(ValueError):
                    self.observe()

    def test_all_journal_fsync_positions(self):
        other = self.candidate_unregistered()
        original = os.fsync
        for operation in ("create", "register", "bind", "observe"):
            for position in range(1, 4 if operation == "create" else 7):
                with self.subTest(operation=operation, fsync=position):
                    label = f"sync-{operation}-{position}"
                    if operation == "create":
                        self.journal = self.root / label
                        self.journal.mkdir(mode=0o700)
                        action = partial(self.api.create_journal, self.journal)
                        count = 0
                    else:
                        self.fresh(label)
                        count = 1
                        if operation == "register":
                            action = partial(
                                self.api.register,
                                self.journal,
                                self.bundles,
                                other.candidate_id,
                            )
                        elif operation == "bind":
                            install_saved_source(
                                self.run_dir,
                                bundle_root=self.bundles,
                                candidate_id=self.c.candidate_id,
                            )
                            action = partial(
                                self.api.bind_run,
                                self.journal,
                                self.c.candidate_id,
                                self.run_dir,
                            )
                        else:
                            self.bind()
                            count = 2
                            self.log(["new", "pre_admitted", "admitted"])
                            action = self.observe
                    calls = 0

                    def failing_sync(fd):
                        nonlocal calls
                        calls += 1
                        if calls == position:
                            raise OSError("injected journal sync failure")
                        return original(fd)

                    with patch("os.fsync", side_effect=failing_sync):
                        with self.assertRaisesRegex(OSError, "injected journal"):
                            action()
                    self.assertEqual(calls, position)
                    names = {p.name for p in self.journal.iterdir()}
                    self.assertFalse(any(n.startswith(".curio-") for n in names))
                    if operation == "create":
                        self.assertEqual(
                            names,
                            {".director.lock"}
                            | ({"journal.json"} if position > 1 else set()),
                        )
                        if position > 1:
                            # Bytes are readable, NOT proof the failed sync succeeded.
                            with patch(
                                "os.fsync", side_effect=AssertionError("read sync")
                            ):
                                self.assertEqual(self.notes(), [])
                        else:
                            with self.assertRaises((ValueError, OSError)):
                                self.notes()
                        with self.assertRaises(ValueError):
                            action()  # creation never repairs the existing root
                        continue
                    stem = f"{count + 1:06d}"
                    self.assertEqual(stem + ".json" in names, position >= 2)
                    self.assertEqual(stem + ".commit" in names, position >= 5)
                    if position in (2, 3, 4):
                        with self.assertRaises(ValueError):
                            self.notes()
                    elif position >= 5:
                        with patch("os.fsync", side_effect=AssertionError("read sync")):
                            notes = self.notes()
                        self.assertEqual(
                            notes[-1]["status"],
                            {
                                "register": "authored",
                                "bind": "installed",
                                "observe": "admitted",
                            }[operation],
                        )
                        with self.assertRaises(ValueError):
                            action()  # complete-looking bytes do not permit retry
                    elif operation == "observe":
                        with self.assertRaisesRegex(ValueError, "uncheckpointed"):
                            self.notes()
                    else:
                        self.assertEqual(self.notes()[0]["status"], "authored")

    def test_exclusive_record_and_commit_publication_races(self):
        other = self.candidate_unregistered()
        original = os.link
        for extension in ("json", "commit"):
            with self.subTest(target=extension):
                self.fresh("race-" + extension)
                name = "000002." + extension
                winner = b"competing writer evidence"
                attempts = []

                def competing_link(src, dst, **kwargs):
                    attempts.append(dst)
                    if dst == name:
                        fd = os.open(
                            dst,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=kwargs["dst_dir_fd"],
                        )
                        try:
                            os.write(fd, winner)
                        finally:
                            os.close(fd)
                    return original(src, dst, **kwargs)

                with patch("os.link", side_effect=competing_link):
                    with self.assertRaises(FileExistsError):
                        self.api.register(
                            self.journal, self.bundles, other.candidate_id
                        )
                self.assertEqual(attempts.count(name), 1)
                self.assertEqual((self.journal / name).read_bytes(), winner)
                with self.assertRaises(ValueError):
                    self.notes()
                self.assertFalse(list(self.journal.glob(".curio-*")))

    def test_process_crash_after_record_before_commit_is_reaped(self):
        other = self.candidate_unregistered()
        script = """import os, sys
from chaos import curio_continuity as api
publish = api.store._publish
def crash(directory, name, raw):
    publish(directory, name, raw)
    if name == "000002.json":
        os._exit(73)
api.store._publish = crash
api.register(*sys.argv[1:])
"""
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(self.journal),
                str(self.bundles),
                other.candidate_id,
            ],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)
        self.assertEqual(process.returncode, 73, (stdout, stderr))
        self.assertTrue((self.journal / "000002.json").exists())
        self.assertFalse((self.journal / "000002.commit").exists())
        with self.assertRaises(ValueError):
            self.notes()
        with self.assertRaises(ValueError):
            self.api.register(self.journal, self.bundles, other.candidate_id)

    def test_lifecycle_literal_outcomes(self):
        cases = [
            ([], False, "installed"),
            (["new"], False, "installed"),
            (["new", "rejected"], False, "rejected"),
            (["new", "rejected"], True, "rejected"),
            (["new", "pre_admitted", "rejected"], True, "rejected"),
            (["new", "expired"], False, "expired"),
            (["new", "pre_admitted", "admitted"], True, "admitted"),
            (
                ["new", "pre_admitted", "admitted", "placement_unavailable"],
                True,
                "admitted",
            ),
            (["new", "pre_admitted", "admitted", "expired"], True, "expired"),
            (["new", "pre_admitted", "admitted", "placement_failed"], True, "expired"),
            (
                [
                    "new",
                    "pre_admitted",
                    "admitted",
                    "placement_unavailable",
                    "placement_unavailable",
                    "placed",
                ],
                True,
                "placed",
            ),
            (
                [
                    "new",
                    "pre_admitted",
                    "admitted",
                    "placed",
                    "applied requested=-2 actual=-1",
                    "applied requested=0 actual=0",
                    "applied requested=2 actual=0",
                ],
                True,
                "placed",
            ),
        ]
        for i, (chain, used, status) in enumerate(cases):
            with self.subTest(chain=chain, used=used):
                self.fresh(f"lifecycle-{i}")
                self.bind()
                self.log(chain, used=used)
                self.observe()
                self.assertEqual(
                    self.notes(),
                    [
                        dict(
                            candidate_id=self.c.candidate_id,
                            status=status,
                            continuity_note="proposal 0; status=placed is only prose",
                        )
                    ],
                )
                self.assertEqual(
                    (self.run_dir / "curio.lua").read_bytes(), b"-- synthetic 0"
                )
                prompt = compose_prompt(
                    dict(sanity=100, insight=0), prior_notes=self.notes()
                )
                self.assertEqual(
                    json.loads(prompt.prompt)["prior_notes"][0]["status"], status
                )

    def test_lifecycle_invalid_admission_and_apply_matrix(self):
        self.bind()
        prefixes = ["new", "pre_admitted", "admitted", "placed"]
        chains = [
            (["new"], True),
            ([], True),
            (["new", "pre_admitted"], True),
            (["new", "pre_admitted", "admitted"], False),
            (["new", "pre_admitted", "restore", "admitted"], True),
            (["new", "pre_admitted", "expired"], True),
            (prefixes + ["pre_admitted", "admitted"], True),
            (prefixes + ["placed"], True),
            (prefixes + ["expired"], True),
            (["new", "pre_admitted", "admitted", "placement_failed", "expired"], True),
        ]
        for detail in [
            "applied requested=3 actual=2",
            "applied requested=-3 actual=-2",
            "applied requested=1 actual=2",
            "applied requested=-1 actual=1",
            "applied requested=0 actual=1",
            "applied requested=1 actual=-1",
            "applied requested=-1 actual=-2",
            "applied requested=-0 actual=0",
            "applied requested=2 actual=-0",
            "applied requested=+1 actual=1",
            "applied requested=01 actual=1",
            "applied requested=1 actual=1 ",
        ]:
            chains.append((prefixes + [detail], True))
        chains.append((prefixes + ["applied requested=1 actual=1"] * 4, True))
        for index, (chain, used) in enumerate(chains):
            with self.subTest(chain=chain, used=used):
                self.fresh(f"invalid-chain-{index}")
                self.bind()
                self.log(chain, used=used)
                with self.assertRaises(ValueError):
                    self.observe()
        for key, value in [
            ("safe", 1),
            ("turn", 2),
            ("last_id", 1),
            ("spent", 0),
            ("spent", 2),
        ]:
            with self.subTest(final_admission_counter=key, value=value):
                self.fresh(f"admission-{key}-{value}")
                self.bind()
                self.log(["new", "pre_admitted", "admitted"])
                p = self.run_dir / "events.jsonl"
                lines = [json.loads(x) for x in p.read_bytes().splitlines()]
                lines[-1][key] = value
                put(p, b"".join(json.dumps(e).encode() + b"\n" for e in lines))
                with self.assertRaises(ValueError):
                    self.observe()

    def test_individual_rollback_and_valid_restore(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted", "placed"])
        p = self.run_dir / "events.jsonl"
        prefix = p.read_bytes()
        # Protocol-valid synthetic safe-point state after an ordinary whisper.
        checkpoint = json.loads(prefix.splitlines()[-1])
        checkpoint.update(
            seq=5,
            event="safe_point",
            detail="sleep",
            safe=2,
            turn=20,
            spent=2,
            last_id=1,
            budget=0,
        )
        prefix += json.dumps(checkpoint).encode() + b"\n"
        put(p, prefix)
        self.observe()
        restore = dict(checkpoint, seq=6, event="session", detail="restore")
        for key, value in [
            ("seq", 5),
            ("safe", 1),
            ("turn", 19),
            ("spent", 1),
            ("last_id", 0),
        ]:
            with self.subTest(rollback=key):
                bad = dict(restore, **{key: value})
                put(p, prefix + json.dumps(bad).encode() + b"\n")
                with self.assertRaisesRegex(ValueError, "rollback"):
                    self.observe()
        put(p, prefix + json.dumps(restore).encode() + b"\n")
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "placed")
        for detail in ("new", "wrong"):
            with self.subTest(session=detail):
                bad = dict(restore, seq=7, detail=detail)
                put(
                    p,
                    prefix
                    + json.dumps(restore).encode()
                    + b"\n"
                    + json.dumps(bad).encode()
                    + b"\n",
                )
                with self.assertRaises(ValueError):
                    self.observe()
        death = dict(restore, seq=7, event="death", detail="")
        bad = dict(restore, seq=8)
        put(
            p,
            prefix
            + b"".join(json.dumps(e).encode() + b"\n" for e in [restore, death, bad]),
        )
        with self.assertRaisesRegex(ValueError, "death"):
            self.observe()

    def test_plain_source_provenance_never_becomes_bundle_note(self):
        source = self.root / "plain.lua"
        put(source, self.c.lua_source)
        receipt = install_saved_source(self.run_dir, source_file=source)
        self.assertEqual(receipt["provenance"], "supplied_source_file")
        with self.assertRaises(ValueError):
            self.api.bind_run(self.journal, self.c.candidate_id, self.run_dir)
        self.assertEqual(self.notes()[0]["status"], "authored")
        self.assertEqual(len(self.records()), 1)

    def test_run_and_evidence_tamper_disappearance_replacement(self):
        for name in (
            "curio.lua",
            "curio-install.json",
            "curio-used.lua",
            "events.jsonl",
        ):
            for mutation in (
                "content",
                "missing",
                "inode",
                "mode",
                "symlink",
                "hardlink",
            ):
                with self.subTest(file=name, mutation=mutation):
                    self.fresh(f"tamper-{name}-{mutation}")
                    self.bind()
                    self.log(["new", "pre_admitted", "admitted"])
                    self.observe()
                    p = self.run_dir / name
                    raw = p.read_bytes()
                    if mutation == "content":
                        put(p, raw + b" ")
                    elif mutation == "missing":
                        p.unlink()
                    elif mutation == "inode":
                        replacement = self.run_dir / "replacement"
                        put(replacement, raw)
                        replacement.replace(p)
                    elif mutation == "mode":
                        p.chmod(0o644)
                    elif mutation == "symlink":
                        target = self.run_dir / "target"
                        p.rename(target)
                        p.symlink_to(target)
                    else:
                        os.link(p, self.run_dir / "second-link")
                    with self.assertRaises((ValueError, OSError)):
                        self.notes()
                    with self.assertRaises((ValueError, OSError)):
                        self.observe()
        for mutation in ("missing", "copied", "symlink"):
            with self.subTest(run_directory=mutation):
                self.fresh("directory-" + mutation)
                self.bind()
                old = self.root / ("old-" + mutation)
                self.run_dir.rename(old)
                if mutation == "copied":
                    shutil.copytree(old, self.run_dir)
                elif mutation == "symlink":
                    self.run_dir.symlink_to(old, target_is_directory=True)
                with self.assertRaises((ValueError, OSError)):
                    self.notes()

    def test_first_bind_proof_requires_run_schema(self):
        self.bind()
        records = self.records()
        records[1]["proof"]["run"] = None
        self.rewrite(records)
        with self.assertRaises(ValueError):
            self.notes()

    def test_snapshot_disappearance_and_cross_file_changes_reject(self):
        for name in (
            "curio.lua",
            "curio-install.json",
            "curio-used.lua",
            "events.jsonl",
        ):
            with self.subTest(changed_after_snapshot=name):
                self.fresh("snapshot-" + name)
                self.bind()
                self.log(["new", "pre_admitted", "admitted"])
                original = self.api._file
                changed = False

                def raced_file(directory, filename, cap):
                    nonlocal changed
                    result = original(directory, filename, cap)
                    if filename == "events.jsonl" and not changed:
                        changed = True
                        path = self.run_dir / name
                        put(path, path.read_bytes() + b" ")
                    return result

                with patch.object(self.api, "_file", side_effect=raced_file):
                    with self.assertRaises(ValueError):
                        self.api._evidence(
                            self.bundles, self.c.candidate_id, str(self.run_dir)
                        )
        for name in ("curio.lua", "curio-install.json"):
            with self.subTest(disappeared_after_verify=name):
                self.fresh("disappear-" + name)
                self.bind()
                original = self.api.store._verify

                def raced_verify(*args):
                    result = original(*args)
                    (self.run_dir / name).unlink()
                    return result

                with patch.object(self.api.store, "_verify", side_effect=raced_verify):
                    with self.assertRaises((ValueError, OSError)):
                        self.api._evidence(
                            self.bundles, self.c.candidate_id, str(self.run_dir)
                        )

    def test_run_replaced_during_snapshot_rejects(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        original = self.api._file
        changed = False

        def raced_file(directory, name, cap):
            nonlocal changed
            result = original(directory, name, cap)
            if name == "events.jsonl" and not changed:
                changed = True
                old = self.root / "renamed-live-run"
                self.run_dir.rename(old)
                shutil.copytree(old, self.run_dir)
            return result

        with patch.object(self.api, "_file", side_effect=raced_file):
            with self.assertRaises(ValueError):
                self.api._evidence(self.bundles, self.c.candidate_id, str(self.run_dir))

    def test_production_record_count_and_note_selection_boundaries(self):
        self.assertEqual(self.api.MAX_RECORDS, 128)
        candidates = [self.c] + [self.candidate(i) for i in range(1, 128)]
        expected = [
            dict(
                candidate_id=c.candidate_id,
                status="authored",
                continuity_note=f"proposal {i}; status=placed is only prose",
            )
            for i, c in enumerate(candidates)
        ][-6:]
        self.assertEqual(len(self.records()), 128)
        self.assertEqual(len(list(self.journal.iterdir())), 258)
        self.assertEqual(self.notes(), expected)
        self.assertEqual(self.api.prior_notes(self.journal, limit=6), expected)
        self.assertEqual(self.api.prior_notes(self.journal, limit=0), [])
        self.assertEqual(self.api.prior_notes(self.journal, limit=1), expected[-1:])
        for limit in (-1, 7, 128, True, 1.0, "6", None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.api.prior_notes(self.journal, limit=limit)
        other = self.candidate_unregistered()
        with self.assertRaisesRegex(ValueError, "record cap"):
            self.api.register(self.journal, self.bundles, other.candidate_id)
        self.assertFalse((self.journal / "000129.json").exists())
        # Age/selection must not hide the oldest raw evidence, even at limit zero.
        put(self.bundles / self.c.candidate_id / "continuity-note.txt", b"old tamper")
        for limit in (0, 6):
            with self.subTest(tampered_old_limit=limit), self.assertRaises(ValueError):
                self.api.prior_notes(self.journal, limit=limit)

    def test_production_record_byte_boundary(self):
        self.assertEqual(self.api.MAX_RECORD_BYTES, 16384)
        p = self.journal / "000001.json"
        raw = p.read_bytes()
        exact = raw + b" " * (16384 - len(raw))
        put(p, exact)
        put(p.with_suffix(".commit"), hashlib.sha256(exact).hexdigest().encode())
        self.assertEqual(self.notes()[0]["status"], "authored")
        over = exact + b" "
        put(p, over)
        put(p.with_suffix(".commit"), hashlib.sha256(over).hexdigest().encode())
        with self.assertRaisesRegex(ValueError, "byte cap"):
            self.notes()
        # Production valid record schemas cannot naturally fill 16 KiB. Exercise
        # writer length guard with controlled serialization, never accept opaque
        # oversized proof fields as an API-supported schema.
        self.rewrite([json.loads(raw)])
        other = self.candidate_unregistered()
        encode = self.api.store._encode

        def padded(obj):
            result = encode(obj)
            if obj.get("op") == "register":
                result += b" " * (16385 - len(result))
            return result

        with patch.object(self.api.store, "_encode", side_effect=padded):
            with self.assertRaisesRegex(ValueError, "record byte cap"):
                self.api.register(self.journal, self.bundles, other.candidate_id)
        self.assertFalse((self.journal / "000002.json").exists())

    def generic_log(self, count, line_bytes=None):
        # JSON whitespace padding tests transport bounds without inventing event
        # fields or overlong native detail. This is protocol-valid synthetic data.
        template = json.loads(events(["new"]))
        lines = []
        for seq in range(1, count + 1):
            e = dict(
                template,
                seq=seq,
                event="session" if seq == 1 else "eat",
                phase="result" if seq == 1 else "attempt",
                detail="new" if seq == 1 else "",
            )
            line = json.dumps(e, separators=(",", ":")).encode()
            if line_bytes is not None:
                self.assertLessEqual(len(line), line_bytes)
                line += b" " * (line_bytes - len(line))
            lines.append(line + b"\n")
        return b"".join(lines)

    def test_production_event_count_boundary(self):
        self.assertEqual(self.api.MAX_EVENTS, 4096)
        self.bind()
        raw = self.generic_log(4096)
        self.assertLess(len(raw), 1048576)
        put(self.run_dir / "events.jsonl", raw)
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "installed")
        raw = self.generic_log(4097)
        self.assertLess(len(raw), 1048576)
        put(self.run_dir / "events.jsonl", raw)
        with self.assertRaisesRegex(ValueError, "event count cap"):
            self.observe()
        with self.assertRaises(ValueError):
            self.notes()

    def test_production_event_byte_boundary(self):
        self.assertEqual(self.api.MAX_EVENT_BYTES, 1048576)
        self.bind()
        raw = self.generic_log(256, line_bytes=4095)
        self.assertEqual(len(raw), 1048576)
        put(self.run_dir / "events.jsonl", raw)
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "installed")
        # Still complete JSON lines, each <=4096 bytes; only total grows by one.
        raw = raw[:-1] + b" \n"
        self.assertEqual(len(raw), 1048577)
        put(self.run_dir / "events.jsonl", raw)
        with self.assertRaisesRegex(ValueError, "byte cap"):
            self.observe()

    def test_production_event_line_boundary(self):
        self.bind()
        raw = self.generic_log(1, line_bytes=4096)
        self.assertEqual(len(raw), 4097)  # excludes newline from line bound
        put(self.run_dir / "events.jsonl", raw)
        self.observe()
        self.assertEqual(self.notes()[0]["status"], "installed")
        put(self.run_dir / "events.jsonl", self.generic_log(1, line_bytes=4097))
        with self.assertRaisesRegex(ValueError, "event line cap"):
            self.observe()

    def test_real_host_path_utf8_boundary(self):
        # Create the actual deep private path, not a mocked filesystem lookup.
        p = self.root / "long-bundles"
        while len(str(p).encode()) + 102 < 2048:
            p = p / ("x" * 100)
        remaining = 2048 - len(str(p).encode()) - 1
        p = p / ("x" * (remaining - 2) + "é")
        self.assertEqual(len(str(p).encode()), 2048)
        p.mkdir(parents=True, mode=0o700)
        c = store_candidate(
            p, json.dumps(dict(lua_source="-- long path", continuity_note="long"))
        )
        self.api.register(self.journal, p, c.candidate_id)
        self.assertEqual(self.notes()[-1]["continuity_note"], "long")
        over = p.with_name(p.name + "x")
        over.mkdir(mode=0o700)
        c2 = store_candidate(
            over, json.dumps(dict(lua_source="-- over path", continuity_note="no"))
        )
        self.assertEqual(len(str(over).encode()), 2049)
        with self.assertRaisesRegex(ValueError, "host path"):
            self.api.register(self.journal, over, c2.candidate_id)

    def test_read_only_success_and_failure_do_not_mutate(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()

        def snapshot():
            return {
                str(p.relative_to(self.root)): (
                    p.stat().st_ino,
                    p.stat().st_mode,
                    p.stat().st_mtime_ns,
                    p.read_bytes(),
                )
                for p in self.root.rglob("*")
                if p.is_file()
            }

        before = snapshot()
        original_open = os.open

        def readonly_open(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_CREAT | os.O_TRUNC | os.O_EXCL))
            return original_open(path, flags, *args, **kwargs)

        with (
            patch("os.open", side_effect=readonly_open),
            patch("os.fsync", side_effect=AssertionError("read fsync")),
            patch("os.unlink", side_effect=AssertionError("read cleanup")),
            patch("os.write", side_effect=AssertionError("read write")),
        ):
            self.assertEqual(self.notes()[0]["status"], "admitted")
        self.assertEqual(snapshot(), before)
        (self.run_dir / ".director.lock").unlink()
        before = snapshot()
        with (
            patch("os.open", side_effect=readonly_open),
            patch("os.fsync", side_effect=AssertionError("read fsync")),
        ):
            with self.assertRaises(OSError):
                self.notes()
        self.assertEqual(snapshot(), before)
        self.assertFalse((self.run_dir / ".director.lock").exists())

    def test_rehashed_duplicate_observation_is_not_silently_accepted(self):
        self.bind()
        self.log(["new", "pre_admitted", "admitted"])
        self.observe()
        records = self.records()
        duplicate = copy.deepcopy(records[-1])
        duplicate["seq"] = 4
        self.rewrite(records + [duplicate])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.notes()

    def test_updated_old_candidate_does_not_reorder_selected_notes(self):
        self.bind()
        candidates = [self.c] + [self.candidate(i) for i in range(1, 8)]
        self.log(["new", "pre_admitted", "admitted", "placed"])
        self.observe()
        expected = [
            dict(
                candidate_id=c.candidate_id,
                status="authored",
                continuity_note=f"proposal {i}; status=placed is only prose",
            )
            for i, c in enumerate(candidates)
            if i >= 2
        ]
        self.assertEqual(self.notes(), expected)
        # Rehash a checkpoint older than every selected candidate. Checking only
        # latest six records/candidates would miss this earlier invalid proof.
        records = self.records()
        records[1]["proof"]["run"]["identity"] = [0, 0]
        self.rewrite(records)
        with self.assertRaises(ValueError):
            self.notes()


if __name__ == "__main__":
    unittest.main()
