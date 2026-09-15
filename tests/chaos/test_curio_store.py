"""Private, real-filesystem curio evidence fixtures; never native admission."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chaos.curio import AuthoringEnvelope
from chaos.director import Mailbox


RAW_NAME = "raw-response.json"
SOURCE_NAME = "source.lua"
NOTE_NAME = "continuity-note.txt"
MANIFEST_NAME = "manifest.json"
RECEIPT_NAME = "curio-install.json"
ERRORS = (ValueError, OSError)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def envelope(source="not Lua\r\n\f-- café", note="é e\u0301"):
    return (
        " \r\n\t"
        + json.dumps(
            {"lua_source": source, "continuity_note": note}, ensure_ascii=False
        )
        + "\r\n "
    )


def private_file(path, data):
    path.write_bytes(data)
    path.chmod(0o600)
    return path


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="curio7b1-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundles = self.root / "bundles"
        self.run_dir = self.root / "run"
        self.bundles.mkdir(mode=0o700)
        self.run_dir.mkdir(mode=0o700)
        self.raw = envelope()
        self.source = json.loads(self.raw)["lua_source"].encode()
        self.identity = digest(self.source)
        self.bundle = self.bundles / self.identity
        self.input = private_file(self.root / "input.lua", self.source)
        self.store = importlib.import_module("chaos.curio_store")

    def save(self, raw=None):
        return self.store.store_candidate(
            self.bundles, self.raw if raw is None else raw
        )

    def read(self):
        return self.store.read_candidate(self.bundles, self.identity)

    def install(self, **kwargs):
        return self.store.install_saved_source(
            self.run_dir, source_file=self.input, **kwargs
        )

    def snapshot(self, root):
        return {
            str(p.relative_to(root)): (p.read_bytes(), p.stat().st_ino)
            for p in root.rglob("*")
            if p.is_file()
        }

    def test_exact_roundtrip_and_host_manifest(self):
        result = self.save()
        self.assertEqual(result, self.read())
        self.assertEqual(result.candidate_id, self.identity)
        self.assertEqual(result.raw_response, self.raw)
        self.assertEqual(result.lua_source, self.source)
        self.assertEqual(result.continuity_note, "é e\u0301")
        self.assertEqual((self.bundle / RAW_NAME).read_bytes(), self.raw.encode())
        self.assertEqual((self.bundle / SOURCE_NAME).read_bytes(), self.source)
        self.assertEqual((self.bundle / NOTE_NAME).read_bytes(), "é e\u0301".encode())
        manifest = json.loads((self.bundle / MANIFEST_NAME).read_bytes())
        self.assertEqual(
            manifest,
            {
                "version": 1,
                "provenance": "supplied_raw_envelope",
                "candidate_id": self.identity,
                "source_sha256": self.identity,
                "raw_response_sha256": digest(self.raw.encode()),
                "note_sha256": digest("é e\u0301".encode()),
            },
        )
        self.assertEqual(
            {p.name for p in self.bundle.iterdir()},
            {
                RAW_NAME,
                SOURCE_NAME,
                NOTE_NAME,
                MANIFEST_NAME,
            },
        )
        self.assertEqual(stat.S_IMODE(self.bundle.stat().st_mode), 0o700)
        for path in self.bundle.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_nlink, 1)
        with self.assertRaises((AttributeError, TypeError)):
            result.candidate_id = "x"

    def test_existing_complete_or_conflicting_bundle_never_overwritten(self):
        self.save()
        before = self.snapshot(self.bundles)
        for raw in (self.raw, self.raw + " ", envelope(note="different")):
            with self.subTest(raw=raw), self.assertRaises(ERRORS):
                self.save(raw)
            self.assertEqual(self.snapshot(self.bundles), before)

    def test_missing_partial_and_extra_artifact_fail_closed(self):
        with self.assertRaises(ERRORS):
            self.read()
        self.bundle.mkdir(mode=0o700)
        private_file(self.bundle / RAW_NAME, self.raw.encode())
        before = self.snapshot(self.bundles)
        with self.assertRaises(ERRORS):
            self.read()
        with self.assertRaises(ERRORS):
            self.save()
        self.assertEqual(self.snapshot(self.bundles), before)
        # No orphan forgiveness even when a valid bundle has an extra artifact.
        for p in self.bundle.iterdir():
            p.unlink()
        self.bundle.rmdir()
        self.save()
        private_file(self.bundle / ".leftover", b"unfinished")
        with self.assertRaises(ERRORS):
            self.read()

    def test_reject_invalid_envelope_before_creating_evidence(self):
        invalid = [
            "{}",
            '{"lua_source":"x","lua_source":"y","continuity_note":""}',
            envelope(""),
            envelope("x" * 4097),
            envelope("x\0y"),
            envelope(note="bad\f"),
            envelope() + "x" * 8192,
            AuthoringEnvelope(self.raw, b"forged", "forged"),
            {"lua_source": "x", "continuity_note": ""},
        ]
        for raw in invalid:
            with self.subTest(raw=type(raw)), self.assertRaises(ValueError):
                self.save(raw)
            self.assertEqual(list(self.bundles.iterdir()), [])

    def test_bundle_boundary_bytes_and_no_normalization(self):
        for source in ("x", "é" * 2048, "x" * 4096, "\f\r\n\x01\x7f\x85"):
            with self.subTest(length=len(source)):
                result = self.save(envelope(source, ""))
                reread = self.store.read_candidate(
                    self.bundles, digest(source.encode())
                )
                self.assertEqual(result.lua_source, source.encode())
                self.assertEqual(result, reread)

    def test_tampering_each_evidence_file_rejected(self):
        self.save()
        for name in (RAW_NAME, SOURCE_NAME, NOTE_NAME, MANIFEST_NAME):
            path = self.bundle / name
            original = path.read_bytes()
            with self.subTest(name=name):
                private_file(path, original + b"x")
                with self.assertRaises(ERRORS):
                    self.read()
                private_file(path, original)
        # Matching independent hashes are insufficient: decoded raw must bind.
        private_file(self.bundle / SOURCE_NAME, b"forged")
        manifest = json.loads((self.bundle / MANIFEST_NAME).read_bytes())
        manifest["source_sha256"] = digest(b"forged")
        private_file(self.bundle / MANIFEST_NAME, json.dumps(manifest).encode())
        with self.assertRaises(ERRORS):
            self.read()

    def test_strict_manifest_keys_types_and_id_format(self):
        self.save()
        path = self.bundle / MANIFEST_NAME
        original = path.read_bytes()
        valid = json.loads(original)
        invalid = [b"[]", b"{}", original[:-1] + b',"version":1}', b"{" * 2000]
        for key, value in (
            ("version", True),
            ("version", 1.0),
            ("version", 2),
            ("source_sha256", "../outside"),
            ("candidate_id", "A" * 64),
            ("candidate_id", "../" + "a" * 64),
            ("note_sha256", None),
            ("raw_response_sha256", "0" * 64),
            ("path", "../outside"),
            ("status", "admitted"),
            ("provenance", "live_model"),
        ):
            invalid.append(json.dumps({**valid, key: value}).encode())
        for raw in invalid:
            with self.subTest(raw=raw[:100]):
                private_file(path, raw)
                with self.assertRaises(ERRORS):
                    self.read()
        private_file(path, original)
        for identity in ("../x", "A" * 64, "a" * 63, "a" * 65, 1, None):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                self.store.read_candidate(self.bundles, identity)

    def test_fresh_file_install_exact_opaque_bytes_and_receipt(self):
        # A plain saved source need not be UTF-8 or valid Lua/JSON.
        raw = b"\xff\f\r\nnot lua\x01"
        private_file(self.input, raw)
        receipt = self.install()
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), raw)
        self.assertEqual(
            receipt, json.loads((self.run_dir / RECEIPT_NAME).read_bytes())
        )
        self.assertEqual(
            receipt,
            {
                "version": 1,
                "status": "candidate_installed_not_admitted",
                "source_sha256": digest(raw),
                "provenance": "supplied_source_file",
            },
        )
        self.assertEqual(
            {p.name for p in self.run_dir.iterdir()},
            {
                "curio.lua",
                RECEIPT_NAME,
                ".director.lock",
            },
        )
        for path in self.run_dir.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.stat().st_nlink, 1)

    def test_bundle_install_revalidates_disk_not_dataclass(self):
        self.save()
        receipt = self.store.install_saved_source(
            self.run_dir, bundle_root=self.bundles, candidate_id=self.identity
        )
        self.assertEqual(receipt["provenance"], "supplied_raw_envelope")
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), self.source)
        before = self.snapshot(self.run_dir)
        private_file(self.bundle / NOTE_NAME, b"tampered")
        with self.assertRaises(ERRORS):
            self.store.install_saved_source(
                self.run_dir,
                bundle_root=self.bundles,
                candidate_id=self.identity,
                mode="verify",
            )
        self.assertEqual(self.snapshot(self.run_dir), before)

    def test_install_argument_errors_have_no_side_effects(self):
        for args in (
            {},
            {"candidate_id": self.identity},
            {"bundle_root": self.bundles},
            {
                "source_file": self.input,
                "bundle_root": self.bundles,
                "candidate_id": self.identity,
            },
            {"source_file": self.input, "mode": "restore-ish"},
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.store.install_saved_source(self.run_dir, **args)
            self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_plain_source_bounds_preflight_before_external_writes(self):
        for raw in (b"", b"x" * 4097, b"x\0y"):
            private_file(self.input, raw)
            with self.assertRaises(ValueError):
                self.install()
            self.assertEqual(list(self.run_dir.iterdir()), [])
        for raw in (b"x", b"x" * 4096):
            private_file(self.input, raw)
            self.install()
            self.assertEqual((self.run_dir / "curio.lua").read_bytes(), raw)
            for path in self.run_dir.iterdir():
                path.unlink()

    def test_fresh_rejects_every_existing_artifact_same_or_different(self):
        for name in ("curio.lua", "curio-used.lua", RECEIPT_NAME):
            for data in (self.source, b"different"):
                with self.subTest(name=name, data=data):
                    path = private_file(self.run_dir / name, data)
                    before = self.snapshot(self.run_dir)
                    with self.assertRaises(ERRORS):
                        self.install()
                    self.assertEqual(path.read_bytes(), data)
                    self.assertEqual(self.snapshot(self.run_dir)[name], before[name])
                    path.unlink()

    def test_verify_is_read_only_and_requires_complete_evidence(self):
        receipt = self.install()
        before = self.snapshot(self.run_dir)
        with (
            patch.object(os, "write", side_effect=AssertionError("write")),
            patch.object(os, "fsync", side_effect=AssertionError("fsync")),
            patch.object(os, "mkdir", side_effect=AssertionError("mkdir")),
            patch.object(os, "unlink", side_effect=AssertionError("unlink")),
        ):
            self.assertEqual(self.install(mode="verify"), receipt)
        self.assertEqual(self.snapshot(self.run_dir), before)
        private_file(self.run_dir / "curio-used.lua", self.source)
        before = self.snapshot(self.run_dir)
        self.assertEqual(self.install(mode="verify"), receipt)
        self.assertEqual(self.snapshot(self.run_dir), before)
        private_file(self.run_dir / "curio-used.lua", b"conflicting")
        with self.assertRaises(ERRORS):
            self.install(mode="verify")
        self.assertEqual((self.run_dir / "curio-used.lua").read_bytes(), b"conflicting")
        for name in (RECEIPT_NAME, "curio.lua", ".director.lock"):
            path = self.run_dir / name
            data = path.read_bytes()
            path.unlink()
            before = self.snapshot(self.run_dir)
            with self.subTest(missing=name), self.assertRaises(ERRORS):
                self.install(mode="verify")
            self.assertEqual(self.snapshot(self.run_dir), before)
            private_file(path, data)

    def test_verify_rejects_tampered_receipts_or_candidate(self):
        self.install()
        path = self.run_dir / RECEIPT_NAME
        original = path.read_bytes()
        valid = json.loads(original)
        invalid = [b"{}", original[:-1] + b',"version":1}']
        for key, value in (
            ("version", True),
            ("status", "admitted"),
            ("source_sha256", "a" * 64),
            ("extra", "x"),
            ("provenance", "live_model"),
        ):
            invalid.append(json.dumps({**valid, key: value}).encode())
        for raw in invalid:
            private_file(path, raw)
            with self.assertRaises(ERRORS):
                self.install(mode="verify")
        private_file(path, original)
        private_file(self.input, b"different")
        with self.assertRaises(ERRORS):
            self.install(mode="verify")

    def test_active_mailbox_writer_blocks_install_and_verify(self):
        with Mailbox(self.run_dir):
            with self.assertRaises(ERRORS):
                self.install()
        self.assertFalse((self.run_dir / "curio.lua").exists())
        self.install()
        with Mailbox(self.run_dir):
            before = self.snapshot(self.run_dir)
            with self.assertRaises(ERRORS):
                self.install(mode="verify")
            self.assertEqual(self.snapshot(self.run_dir), before)

    def test_unsafe_resource_files_fail_without_blocking_or_writing(self):
        self.input.unlink()
        other = private_file(self.root / "other", b"x")
        makers = {
            "symlink": lambda: self.input.symlink_to(other),
            "fifo": lambda: os.mkfifo(self.input, 0o600),
            "directory": lambda: self.input.mkdir(mode=0o700),
            "hardlink": lambda: os.link(other, self.input),
            "public": lambda: (private_file(self.input, b"x"), self.input.chmod(0o644)),
            "executable": lambda: (
                private_file(self.input, b"x"),
                self.input.chmod(0o700),
            ),
        }
        for name, make in makers.items():
            make()
            with self.subTest(name=name), self.assertRaises(ERRORS):
                self.install()
            self.assertEqual(list(self.run_dir.iterdir()), [])
            if self.input.is_dir() and not self.input.is_symlink():
                self.input.rmdir()
            else:
                self.input.unlink()

    def test_unsafe_bundle_files_and_run_lock_are_rejected(self):
        self.save()
        for name in (RAW_NAME, SOURCE_NAME, NOTE_NAME, MANIFEST_NAME):
            path = self.bundle / name
            original = path.read_bytes()
            for kind in ("mode", "symlink", "fifo", "hardlink"):
                with self.subTest(name=name, kind=kind):
                    if kind == "mode":
                        path.chmod(0o644)
                    else:
                        path.unlink()
                        if kind == "symlink":
                            path.symlink_to(self.input)
                        elif kind == "fifo":
                            os.mkfifo(path, 0o600)
                        else:
                            os.link(self.input, path)
                    with self.assertRaises(ERRORS):
                        self.read()
                    path.unlink()
                    private_file(path, original)
        lock = self.run_dir / ".director.lock"
        os.mkfifo(lock, 0o600)
        with self.assertRaises(ERRORS):
            self.install()
        self.assertFalse((self.run_dir / "curio.lua").exists())

    @unittest.skipUnless(os.getuid() == 0, "requires chown privilege")
    def test_foreign_owned_file_and_directory_rejected(self):
        os.chown(self.input, 65534, -1)
        with self.assertRaises(ERRORS):
            self.install()
        os.chown(self.input, 0, -1)
        os.chown(self.run_dir, 65534, -1)
        try:
            with self.assertRaises(ERRORS):
                self.install()
        finally:
            os.chown(self.run_dir, 0, -1)

    def test_private_directory_validation_including_symlink_ancestors(self):
        for directory in (self.bundles, self.run_dir):
            directory.chmod(0o755)
            with self.subTest(directory=directory), self.assertRaises(ERRORS):
                self.save() if directory == self.bundles else self.install()
            directory.chmod(0o700)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ERRORS):
            self.store.store_candidate(alias / "bundles", self.raw)
        with self.assertRaises(ERRORS):
            self.store.install_saved_source(alias / "run", source_file=self.input)
        with self.assertRaises(ERRORS):
            self.store.install_saved_source(
                self.run_dir, source_file=alias / "input.lua"
            )
        self.assertEqual(list(self.bundles.iterdir()), [])
        self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_oversized_file_rejected_before_read(self):
        with self.input.open("wb") as f:
            f.truncate(1024 * 1024)
        with patch.object(os, "read", side_effect=AssertionError("unbounded read")):
            with self.assertRaises(ValueError):
                self.install()
        self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_no_inference_imports_or_calls(self):
        import builtins

        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if any(word in name for word in ("oauth", "openai", "backend", "httpx")):
                raise AssertionError("inference dependency: " + name)
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=guard):
            importlib.reload(self.store)
            self.save()
            self.install()
            self.install(mode="verify")

    def test_bundle_parent_fsync_failure_preserves_incomplete_publication(self):
        with patch.object(os, "fsync", side_effect=OSError("sync fault")):
            with self.assertRaises(OSError):
                self.save()
        self.assertTrue(self.bundle.is_dir())
        with self.assertRaises(ERRORS):
            self.read()
        with self.assertRaises(ERRORS):
            self.save()

    def test_file_fsync_failure_cleans_only_unpublished_temp(self):
        real_sync = os.fsync

        def fail_file(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("file sync fault")
            real_sync(fd)

        with patch.object(os, "fsync", side_effect=fail_file):
            with self.assertRaises(OSError):
                self.save()
        self.assertEqual(list(self.bundle.iterdir()), [])
        with patch.object(os, "fsync", side_effect=fail_file):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual({p.name for p in self.run_dir.iterdir()}, {".director.lock"})

    def test_directory_fsync_failure_retains_published_source_and_no_receipt(self):
        real_sync = os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("directory sync fault")
            real_sync(fd)

        with patch.object(os, "fsync", side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), self.source)
        self.assertEqual((self.run_dir / "curio.lua").stat().st_nlink, 1)
        self.assertFalse((self.run_dir / RECEIPT_NAME).exists())
        before = self.snapshot(self.run_dir)
        with self.assertRaises(ERRORS):
            self.install()
        with self.assertRaises(ERRORS):
            self.install(mode="verify")
        self.assertEqual(self.snapshot(self.run_dir), before)

    def test_final_receipt_sync_failure_raises_but_preserves_exact_targets(self):
        real_sync = os.fsync

        def fail_final(fd):
            if (
                stat.S_ISDIR(os.fstat(fd).st_mode)
                and (self.run_dir / RECEIPT_NAME).exists()
            ):
                raise OSError("receipt directory sync fault")
            real_sync(fd)

        with patch.object(os, "fsync", side_effect=fail_final):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), self.source)
        self.assertEqual(
            json.loads((self.run_dir / RECEIPT_NAME).read_bytes())["source_sha256"],
            self.identity,
        )
        before = self.snapshot(self.run_dir)
        with self.assertRaises(ERRORS):
            self.install()
        self.assertEqual(self.snapshot(self.run_dir), before)
        # Explicit verification observes bytes, not a recovery/durability claim.
        self.assertEqual(self.install(mode="verify")["source_sha256"], self.identity)

    def test_raced_target_exclusive_publication_never_overwrites(self):
        real_link = os.link

        def race(src, dst, *args, **kwargs):
            if dst == "curio.lua":
                private_file(self.run_dir / "curio.lua", b"raced source")
            return real_link(src, dst, *args, **kwargs)

        with patch.object(os, "link", side_effect=race):
            with self.assertRaises(ERRORS):
                self.install()
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), b"raced source")
        self.assertFalse((self.run_dir / RECEIPT_NAME).exists())
        self.assertFalse(
            any(p.name.startswith(".curio-") for p in self.run_dir.iterdir())
        )

    def test_every_sync_stage_failure_preserves_published_evidence(self):
        real_sync = os.fsync
        for kind in ("bundle", "install"):

            def operation(root):
                if kind == "bundle":
                    return self.store.store_candidate(root, self.raw)
                return self.store.install_saved_source(root, source_file=self.input)

            trace = []
            baseline = self.root / (kind + "-baseline")
            baseline.mkdir(mode=0o700)

            def record(fd):
                trace.append(
                    "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
                )
                real_sync(fd)

            with patch.object(os, "fsync", side_effect=record):
                operation(baseline)
            expected = ["file", "file", "directory"] * (4 if kind == "bundle" else 2)
            if kind == "bundle":
                expected.insert(0, "directory")
            self.assertEqual(trace, expected)
            for fail_at in range(1, len(trace) + 1):
                root = self.root / (kind + "-sync-" + str(fail_at))
                root.mkdir(mode=0o700)
                state = {"calls": 0, "published": {}}

                def fail_sync(fd):
                    state["calls"] += 1
                    if state["calls"] == fail_at:
                        state["published"] = {
                            k: v
                            for k, v in self.snapshot(root).items()
                            if not Path(k).name.startswith(".curio-")
                        }
                        raise OSError("injected sync fault")
                    real_sync(fd)

                with self.subTest(kind=kind, stage=fail_at):
                    with patch.object(os, "fsync", side_effect=fail_sync):
                        with self.assertRaises(OSError):
                            operation(root)
                    self.assertEqual(self.snapshot(root), state["published"])
                    if kind == "bundle" or (root / "curio.lua").exists():
                        before = self.snapshot(root)
                        with self.assertRaises(ERRORS):
                            operation(root)
                        self.assertEqual(self.snapshot(root), before)

    def test_process_crash_after_link_retains_ambiguous_two_link_source(self):
        script = """
import os, sys
from chaos.curio_store import install_saved_source
link = os.link
def crash(src, dst, **kwargs):
    link(src, dst, **kwargs)
    if dst == 'curio.lua':
        os._exit(73)
os.link = crash
install_saved_source(sys.argv[1], source_file=sys.argv[2])
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(self.run_dir), str(self.input)],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), self.source)
        self.assertEqual((self.run_dir / "curio.lua").stat().st_nlink, 2)
        self.assertFalse((self.run_dir / RECEIPT_NAME).exists())
        self.assertEqual(len(list(self.run_dir.glob(".curio-*"))), 1)
        before = self.snapshot(self.run_dir)
        for mode in ("fresh", "verify"):
            with self.assertRaises(ERRORS):
                self.install(mode=mode)
            self.assertEqual(self.snapshot(self.run_dir), before)

    def test_read_growth_or_entry_replacement_rejected_before_install_writes(self):
        real_read = os.read
        for kind in ("growth", "replacement"):
            private_file(self.input, self.source)
            changed = False

            def race(fd, size):
                nonlocal changed
                if not changed:
                    changed = True
                    if kind == "growth":
                        with self.input.open("ab") as f:
                            f.write(b"x" * 4097)
                    else:
                        self.input.unlink()
                        private_file(self.input, b"replacement")
                return real_read(fd, size)

            with self.subTest(kind=kind), patch.object(os, "read", side_effect=race):
                with self.assertRaises(ValueError):
                    self.install()
            self.assertEqual(list(self.run_dir.iterdir()), [])

    def test_verify_rejects_unsafe_installed_resources(self):
        self.install()
        private_file(self.run_dir / "curio-used.lua", self.source)
        for name in (*("curio.lua", "curio-used.lua", RECEIPT_NAME), ".director.lock"):
            path = self.run_dir / name
            original = path.read_bytes()
            for kind in ("mode", "symlink", "fifo", "hardlink", "directory"):
                with self.subTest(name=name, kind=kind):
                    path.unlink()
                    if kind == "mode":
                        private_file(path, original).chmod(0o644)
                    elif kind == "symlink":
                        path.symlink_to(self.input)
                    elif kind == "fifo":
                        os.mkfifo(path, 0o600)
                    elif kind == "directory":
                        path.mkdir(mode=0o700)
                    else:
                        os.link(self.input, path)
                    with self.assertRaises(ERRORS):
                        self.install(mode="verify")
                    if kind == "directory":
                        path.rmdir()
                    else:
                        path.unlink()
                    private_file(path, original)

    def test_new_lock_contention_in_other_process(self):
        with Mailbox(self.run_dir):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from chaos.curio_store import install_saved_source; import sys; "
                    "install_saved_source(sys.argv[1], source_file=sys.argv[2])",
                    str(self.run_dir),
                    str(self.input),
                ],
                cwd=Path(__file__).resolve().parents[2],
                capture_output=True,
                timeout=5,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"another director", result.stderr)
        self.assertFalse((self.run_dir / "curio.lua").exists())

    def test_directory_symlink_leaf_and_existing_bundle_mode(self):
        self.save()
        self.bundle.chmod(0o755)
        with self.assertRaises(ERRORS):
            self.read()
        self.bundle.chmod(0o700)
        for target, action in (
            (self.bundles, lambda p: self.store.read_candidate(p, self.identity)),
            (
                self.run_dir,
                lambda p: self.store.install_saved_source(p, source_file=self.input),
            ),
        ):
            alias = self.root / "leaf-alias"
            alias.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ERRORS):
                action(alias)
            alias.unlink()

    def test_exclusive_link_and_cleanup_syscall_faults(self):
        for syscall in ("link", "unlink"):
            directory = self.root / ("fault-" + syscall)
            directory.mkdir(mode=0o700)
            with patch.object(os, syscall, side_effect=OSError(syscall + " fault")):
                with self.assertRaises(OSError):
                    self.store.install_saved_source(directory, source_file=self.input)
            if syscall == "link":
                self.assertEqual(
                    {p.name for p in directory.iterdir()}, {".director.lock"}
                )
            else:
                self.assertEqual((directory / "curio.lua").read_bytes(), self.source)
                self.assertEqual((directory / "curio.lua").stat().st_nlink, 2)
                self.assertFalse((directory / RECEIPT_NAME).exists())
                before = self.snapshot(directory)
                with self.assertRaises(ERRORS):
                    self.store.install_saved_source(directory, source_file=self.input)
                self.assertEqual(self.snapshot(directory), before)

    def test_short_write_and_write_failure(self):
        real_write = os.write
        with patch.object(os, "write", side_effect=lambda fd, b: real_write(fd, b[:3])):
            self.save()
            self.install()
        self.assertEqual(self.read().lua_source, self.source)
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), self.source)
        # New private run only: fault must not remove previous evidence.
        second = self.root / "second"
        second.mkdir(mode=0o700)
        before = self.snapshot(self.run_dir)
        with patch.object(os, "write", side_effect=OSError("write fault")):
            with self.assertRaises(OSError):
                self.store.install_saved_source(second, source_file=self.input)
        self.assertEqual({p.name for p in second.iterdir()}, {".director.lock"})
        self.assertEqual(self.snapshot(self.run_dir), before)


if __name__ == "__main__":
    unittest.main()
