"""Synthetic subprocess fixtures: never native builds or hosted acceptance."""

from contextlib import contextmanager
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare_native_ci.py"
REV = "a" * 40
OLD = "4610d90612e3c255b37786e385d86f981b016bc2"
BASELINE = "fd7a91deb1dc33244e0f72a47d3a4ec584255852"
COMPILER = "cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0\n"
FLAGS = "-I/usr/include/lua5.4 -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=600 -llua5.4 -lncursesw -ltinfo\n"


class NativeCIPreparationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "checked native CI preparer is missing")
        spec = importlib.util.spec_from_file_location("ci_builder_unit", SCRIPT)
        self.ci = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ci)
        self.tmp = tempfile.TemporaryDirectory(prefix="native-ci-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "checkout"
        self.root.mkdir()
        (self.root / "GNUmakefile").write_text("# synthetic: never execute\n")
        self.out = self.base / "output with spaces"
        self.calls = []
        self.dirty = ""
        self.shallow = "false"
        self.index = "H GNUmakefile\0"
        self.compiler = COMPILER
        self.build_failure = False
        self.runner = patch.object(self.ci.subprocess, "run", side_effect=self.run_fake)
        self.runner.start()
        self.addCleanup(self.runner.stop)
        self.build_runner = patch.object(
            self.ci, "_run_build", side_effect=self.run_fake
        )
        self.build_runner.start()
        self.addCleanup(self.build_runner.stop)
        self.selection = patch.object(
            self.ci, "verify_selection", return_value={"unit": True}
        )
        self.selection.start()
        self.addCleanup(self.selection.stop)

    def run_fake(self, argv, **kw):
        self.calls.append((argv, kw))
        cwd = Path(kw["cwd"])
        text = ""
        code = 0
        if argv[0] == "/usr/bin/git":
            args = argv[1:]
            if args[:1] == ["clone"]:
                old = Path(args[-1])
                old.mkdir()
                (old / "GNUmakefile").write_text("# synthetic historical source\n")
            elif args == ["rev-parse", "HEAD"]:
                text = OLD if cwd.name == "old-checkout" else REV
            elif args == ["rev-parse", "HEAD^{tree}"]:
                text = "b" * 40
            elif args == ["rev-parse", "--is-shallow-repository"]:
                text = self.shallow
            elif args[:1] == ["status"]:
                text = self.dirty
            elif args == ["ls-files", "-v", "-z"]:
                text = self.index
            elif args == ["ls-files", "-z"]:
                text = "GNUmakefile\0"
            elif args[:1] == ["rev-parse"]:
                text = args[-1].removesuffix("^{commit}")
        elif argv == ["/usr/bin/cc", "--version"]:
            text = self.compiler
        elif argv[0] == "/usr/bin/pkg-config":
            text = FLAGS
        elif argv[0] == "/usr/bin/make":
            code = 7 if self.build_failure else 0
            kw["stdout"].write(b"synthetic unit command output\n")
            if not code and argv[2] == "install":
                mode = argv[3][-1]
                (cwd / ".chaos-build").write_text(mode + "\n")
                for directory in (
                    "src",
                    "dat",
                    "include",
                    "util",
                    "sys",
                    "win",
                    "dnethackdir",
                ):
                    (cwd / directory).mkdir(exist_ok=True)
                (cwd / "include/date.h").write_text("synthetic header " + mode)
                (cwd / "src/main.o").write_text("synthetic object " + mode)
                for name, relative in self.ci.PAIRS.items():
                    data = ("synthetic " + str(cwd) + mode + name).encode()
                    (cwd / relative).write_bytes(data)
                    (cwd / "dnethackdir" / name).write_bytes(data)
        elif argv[0] == "/usr/bin/nm":
            mode = (cwd / ".chaos-build").read_text().strip()
            if cwd.name != "old-checkout" and mode == "1":
                text = "0001 0061 t inert_bones_curios\n0002 0010 T chaos_curio_init\n"
        elif argv[0] == "/usr/bin/readelf":
            text = "synthetic ELF notes, not an ELF measurement\n"
        else:
            self.fail("unexpected command: " + repr(argv))
        if kw.get("check") and code:
            raise subprocess.CalledProcessError(code, argv)
        return subprocess.CompletedProcess(argv, code, stdout=text, stderr="")

    def prepare(self):
        return self.ci.prepare(self.root, self.out, REV)

    def test_real_recipe_environment_and_authenticated_old_checkout(self):
        self.prepare()
        builds = [(a, k) for a, k in self.calls if a[0] == "/usr/bin/make"]
        self.assertEqual(len(builds), 6)
        self.assertEqual(
            [a[3] for a, _ in builds],
            ["CHAOS=1"] * 2 + ["CHAOS=0"] * 2 + ["CHAOS=1"] * 2,
        )
        for index, (argv, kw) in enumerate(builds):
            self.assertEqual(
                argv,
                [
                    "/usr/bin/make",
                    "-j2",
                    ("clean", "install")[index % 2],
                    argv[3],
                    "CC=/usr/bin/cc",
                    "PKG_CONFIG=/usr/bin/pkg-config",
                ],
            )
            self.assertEqual(
                set(kw["env"]), {"PATH", "HOME", "LANG", "TZ", "PKG_CONFIG_LIBDIR"}
            )
            self.assertEqual(kw["env"]["PATH"], "/usr/bin:/bin")
            self.assertEqual(kw["env"]["TZ"], "America/New_York")
            self.assertNotIn("shell", kw)
        clone = next(a for a, _ in self.calls if a[1:2] == ["clone"])
        self.assertIn("--no-hardlinks", clone)
        self.assertIn("--no-checkout", clone)
        self.assertIn(
            ["/usr/bin/git", "checkout", "--detach", OLD], [a for a, _ in self.calls]
        )
        self.assertIn(
            ["/usr/bin/git", "rev-parse", BASELINE + "^{commit}"],
            [a for a, _ in self.calls],
        )
        self.assertEqual(
            json.loads((self.out / "old-on/1-manifest.json").read_text())["revision"],
            OLD,
        )
        done = json.loads((self.out / "system-gcc13/completion.json").read_text())
        self.assertEqual(done["finished_modes"], [0, 1])
        self.assertTrue(done["protected_unchanged"])
        self.assertTrue(done["protected_after"])
        manifest = json.loads((self.out / "system-gcc13/1-manifest.json").read_text())
        self.assertEqual(
            manifest["generated_headers"]["include/date.h"],
            self.ci.digest(self.root / "include/date.h"),
        )
        self.assertTrue(manifest["objects"])
        self.assertEqual(
            manifest["pairs"]["dnethack"]["sha256"],
            self.ci.digest(self.root / "dnethackdir/dnethack"),
        )

    def test_simulated_date_headers_survive_next_mode_and_stay_separate(self):
        """Raw simulated unit files, not native headers or build acceptance."""
        raw = {
            ("old-checkout", 1): b"simulated historical precurio\r\n\x00\xff",
            ("checkout", 0): b"simulated mode zero\r\n\x00\xfe",
            ("checkout", 1): b"simulated mode one\n\x00\xfd",
        }

        def install_raw(argv, **kw):
            cwd = Path(kw["cwd"])
            mode = int(argv[3][-1])
            if cwd == self.root and argv[2:4] == ["clean", "CHAOS=1"]:
                self.assertTrue((self.out / "system-gcc13/0-date.h").is_file())
                self.assertEqual(
                    (self.out / "system-gcc13/0-date.h").read_bytes(),
                    raw[("checkout", 0)],
                )
            result = self.run_fake(argv, **kw)
            if argv[2] == "install":
                (cwd / "include/date.h").write_bytes(raw[(cwd.name, mode)])
            return result

        self.ci._run_build.side_effect = install_raw
        self.prepare()
        for folder, checkout, mode, revision in (
            ("old-on", "old-checkout", 1, OLD),
            ("system-gcc13", "checkout", 0, REV),
            ("system-gcc13", "checkout", 1, REV),
        ):
            with self.subTest(folder=folder, mode=mode):
                capture = self.out / folder / f"{mode}-date.h"
                self.assertEqual(capture.read_bytes(), raw[(checkout, mode)])
                self.assertEqual(stat.S_IMODE(capture.stat().st_mode), 0o600)
                manifest = json.loads(
                    (capture.parent / f"{mode}-manifest.json").read_text()
                )
                self.assertEqual(manifest["mode"], mode)
                self.assertEqual(manifest["revision"], revision)
                self.assertEqual(
                    self.ci.digest(capture),
                    manifest["generated_headers"]["include/date.h"],
                )
                self.assertEqual(
                    set(manifest),
                    {
                        "mode",
                        "revision",
                        "pairs",
                        "symbols",
                        "generated_headers",
                        "objects",
                        "commands",
                        "finished_eastern",
                        "acceptance",
                    },
                )
        self.assertEqual(
            (self.root / "include/date.h").read_bytes(), raw[("checkout", 1)]
        )

    def test_simulated_date_capture_is_private_with_permissive_umask(self):
        receipts = self.base / "unit-receipts"
        receipts.mkdir(mode=0o700)
        old_umask = os.umask(0)
        try:
            self.ci.build_mode(self.root, receipts, REV, self.ci.environment(), 0)
        finally:
            os.umask(old_umask)
        self.assertTrue((receipts / "0-date.h").is_file())
        self.assertEqual(stat.S_IMODE((receipts / "0-date.h").stat().st_mode), 0o600)

    def test_simulated_date_capture_failures_prevent_success_manifest(self):
        """Inject only unit-file faults; all build commands remain mocked."""
        real_digest = self.ci.digest
        for mode in (0, 1):
            for fault in (
                "missing-source",
                "mismatch",
                "missing-capture",
                "exists",
                "symlink",
            ):
                with self.subTest(mode=mode, fault=fault):
                    self.out = self.base / f"output-{mode}-{fault}"
                    receipts = self.out / "system-gcc13"
                    capture = receipts / f"{mode}-date.h"
                    sentinel = self.base / f"sentinel-{mode}-{fault}"
                    sentinel.write_bytes(b"preserve simulated unit sentinel")

                    def install_fault(argv, **kw):
                        result = self.run_fake(argv, **kw)
                        if Path(kw["cwd"]) == self.root and argv[2:4] == [
                            "install",
                            f"CHAOS={mode}",
                        ]:
                            if fault == "missing-source":
                                (self.root / "include/date.h").unlink()
                                (self.root / "include/other.h").write_bytes(b"unit")
                            elif fault == "exists":
                                capture.write_bytes(sentinel.read_bytes())
                            elif fault == "symlink":
                                capture.symlink_to(sentinel)
                        return result

                    def digest_fault(path):
                        if path == capture:
                            if fault == "mismatch":
                                path.write_bytes(b"corrupted simulated capture")
                            elif fault == "missing-capture":
                                path.unlink()
                        return real_digest(path)

                    self.ci._run_build.side_effect = install_fault
                    with patch.object(self.ci, "digest", side_effect=digest_fault):
                        with self.assertRaises((RuntimeError, OSError)):
                            self.prepare()
                    self.assertFalse((receipts / f"{mode}-manifest.json").exists())
                    self.assertFalse((self.out / "preparation.json").exists())
                    completion = json.loads((receipts / "completion.json").read_text())
                    self.assertEqual(
                        completion["finished_modes"], [] if mode == 0 else [0]
                    )
                    self.assertEqual(
                        sentinel.read_bytes(), b"preserve simulated unit sentinel"
                    )
                    if fault in ("exists", "symlink"):
                        self.assertEqual(capture.read_bytes(), sentinel.read_bytes())
                    if fault == "symlink":
                        self.assertTrue(capture.is_symlink())

    def test_private_receipts_writable_copies_and_immutable_archive(self):
        self.prepare()
        for directory in (self.out, self.out / "fixtures", self.out / "system-gcc13"):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for p in (self.out / "system-gcc13").glob("*.json"):
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual((self.out / "MAIL").read_bytes(), b"")
        self.assertEqual(stat.S_IMODE((self.out / "MAIL").stat().st_mode), 0o600)
        for name in self.ci.PAIRS:
            stock, archive = self.out / "stock" / name, self.out / "off-archive" / name
            self.assertEqual(stock.read_bytes(), archive.read_bytes())
            self.assertNotEqual(stock.stat().st_ino, archive.stat().st_ino)
            self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o444)
            self.assertEqual(
                stat.S_IMODE(stock.stat().st_mode),
                0o755 if name == "dnethack" else 0o644,
            )
            copied = self.base / name
            shutil.copy2(stock, copied)
            shutil.copy2(self.root / "dnethackdir" / name, copied)
            self.assertEqual(
                stat.S_IMODE((self.out / "precurio" / name).stat().st_mode),
                0o755 if name == "dnethack" else 0o644,
            )

    def test_failed_build_records_actual_failure_without_success(self):
        self.build_failure = True
        with self.assertRaises(RuntimeError):
            self.prepare()
        commands = json.loads((self.out / "old-on/1-commands.json").read_text())
        self.assertEqual(commands[0]["exit_code"], 7)
        self.assertFalse((self.out / "old-on/1-manifest.json").exists())
        self.assertFalse((self.out / "preparation.json").exists())
        self.assertFalse((self.out / "system-gcc13/1-manifest.json").exists())

    def test_current_install_failure_retains_off_receipts_without_success(self):
        def fail_current_install(argv, **kw):
            result = self.run_fake(argv, **kw)
            if Path(kw["cwd"]) == self.root and argv[2:4] == ["install", "CHAOS=1"]:
                result.returncode = 23
            return result

        self.ci._run_build.side_effect = fail_current_install
        with self.assertRaisesRegex(RuntimeError, "build failed \\(23\\)"):
            self.prepare()
        receipts = self.out / "system-gcc13"
        commands = json.loads((receipts / "1-commands.json").read_text())
        self.assertEqual([c["exit_code"] for c in commands], [0, 23])
        self.assertEqual(
            json.loads((receipts / "completion.json").read_text())["finished_modes"],
            [0],
        )
        self.assertTrue((receipts / "0-manifest.json").exists())
        self.assertFalse((receipts / "1-manifest.json").exists())
        self.assertFalse((self.out / "preparation.json").exists())

    def test_unverified_cleanup_skips_final_input_measurement(self):
        timeout = subprocess.TimeoutExpired(["/usr/bin/make"], 480)
        timeout._build_cleanup_failed = True
        self.ci._run_build.side_effect = timeout
        with patch.object(
            self.ci, "protected_inputs", wraps=self.ci.protected_inputs
        ) as inputs:
            with self.assertRaises(subprocess.TimeoutExpired) as caught:
                self.prepare()
        self.assertIs(caught.exception, timeout)
        self.assertEqual(inputs.call_count, 1)
        receipts = self.out / "old-on"
        self.assertFalse((receipts / "completion.json").exists())
        failure = json.loads((receipts / "preservation-failure.json").read_text())
        self.assertIn("cleanup unverified", failure["preservation_error"])

    def test_command_receipt_failure_preserves_unverified_cleanup_timeout(self):
        timeout = subprocess.TimeoutExpired(["/usr/bin/make"], 480)
        timeout._build_cleanup_failed = True
        self.ci._run_build.side_effect = timeout
        real_save = self.ci.save
        attempted = []

        def fail_command_receipt(path, value):
            if path.name.endswith("-commands.json"):
                attempted.append(value)
                raise OSError("command receipt unavailable")
            return real_save(path, value)

        with (
            patch.object(self.ci, "save", side_effect=fail_command_receipt),
            patch.object(
                self.ci, "protected_inputs", wraps=self.ci.protected_inputs
            ) as inputs,
            self.assertRaises(BaseException) as caught,
        ):
            self.prepare()
        self.assertIs(caught.exception, timeout)
        self.assertTrue(caught.exception._build_cleanup_failed)
        self.assertTrue(
            any("command receipt unavailable" in note for note in timeout.__notes__)
        )
        self.assertEqual(inputs.call_count, 1)
        self.assertEqual(len(attempted), 1)
        self.assertIsNone(attempted[0][0]["exit_code"])
        receipts = self.out / "old-on"
        self.assertFalse((receipts / "1-commands.json").exists())
        self.assertFalse((receipts / "completion.json").exists())
        failure = json.loads((receipts / "preservation-failure.json").read_text())
        self.assertEqual(failure["primary_error"], repr(timeout))
        self.assertIn("cleanup unverified", failure["preservation_error"])
        self.assertFalse((receipts / "1-manifest.json").exists())
        self.assertFalse((self.out / "preparation.json").exists())

    def test_command_receipt_failure_rejects_successful_command(self):
        receipt_error = OSError("command receipt unavailable")
        real_save = self.ci.save
        attempted = []

        def fail_command_receipt(path, value):
            if path.name.endswith("-commands.json"):
                attempted.append(value)
                raise receipt_error
            return real_save(path, value)

        with (
            patch.object(self.ci, "save", side_effect=fail_command_receipt),
            self.assertRaises(OSError) as caught,
        ):
            self.prepare()
        self.assertIs(caught.exception, receipt_error)
        self.assertEqual(len(attempted), 1)
        self.assertEqual(attempted[0][0]["exit_code"], 0)
        self.assertEqual(self.ci._run_build.call_count, 1)
        receipts = self.out / "old-on"
        completion = json.loads((receipts / "completion.json").read_text())
        self.assertEqual(completion["finished_modes"], [])
        self.assertFalse((receipts / "1-manifest.json").exists())
        self.assertFalse((self.out / "preparation.json").exists())

    def test_log_close_failure_preserves_unverified_cleanup_timeout(self):
        real_open = Path.open
        real_save = self.ci.save

        @contextmanager
        def failing_log(path, *args, **kwargs):
            try:
                with real_open(path, *args, **kwargs) as stream:
                    yield stream
            finally:
                raise OSError("log close failed")

        def open_log(path, *args, **kwargs):
            if path.name.endswith(".log"):
                return failing_log(path, *args, **kwargs)
            return real_open(path, *args, **kwargs)

        for receipt_fails in (False, True):
            with self.subTest(receipt_fails=receipt_fails):
                self.out = self.base / f"output-{receipt_fails}"
                timeout = subprocess.TimeoutExpired(["/usr/bin/make"], 480)
                timeout._build_cleanup_failed = True
                self.ci._run_build.side_effect = timeout

                def save_receipt(path, value):
                    if receipt_fails and path.name.endswith("-commands.json"):
                        raise OSError("command receipt unavailable")
                    return real_save(path, value)

                with (
                    patch.object(Path, "open", new=open_log),
                    patch.object(self.ci, "save", side_effect=save_receipt),
                    patch.object(
                        self.ci, "protected_inputs", wraps=self.ci.protected_inputs
                    ) as inputs,
                    self.assertRaises(BaseException) as caught,
                ):
                    self.prepare()
                self.assertIs(caught.exception, timeout)
                self.assertTrue(caught.exception._build_cleanup_failed)
                self.assertTrue(
                    any("log close failed" in note for note in timeout.__notes__)
                )
                if receipt_fails:
                    self.assertTrue(
                        any(
                            "command receipt unavailable" in note
                            for note in timeout.__notes__
                        )
                    )
                self.assertEqual(inputs.call_count, 1)
                receipts = self.out / "old-on"
                if not receipt_fails:
                    commands = json.loads((receipts / "1-commands.json").read_text())
                    self.assertIsNone(commands[0]["exit_code"])
                self.assertFalse((receipts / "completion.json").exists())
                failure = json.loads(
                    (receipts / "preservation-failure.json").read_text()
                )
                self.assertEqual(failure["primary_error"], repr(timeout))
                self.assertIn("cleanup unverified", failure["preservation_error"])
                self.assertFalse((receipts / "1-manifest.json").exists())
                self.assertFalse((self.out / "preparation.json").exists())

    def test_deleted_input_does_not_mask_primary_timeout(self):
        timeout = subprocess.TimeoutExpired(["/usr/bin/make"], 480)

        def delete_then_timeout(argv, **kw):
            (Path(kw["cwd"]) / "GNUmakefile").unlink()
            raise timeout

        self.ci._run_build.side_effect = delete_then_timeout
        with self.assertRaises(subprocess.TimeoutExpired) as caught:
            self.prepare()
        self.assertIs(caught.exception, timeout)
        receipts = self.out / "old-on"
        diagnostic = receipts / "preservation-failure.json"
        failure = json.loads(diagnostic.read_text())
        self.assertIn("FileNotFoundError", failure["preservation_error"])
        self.assertIn("GNUmakefile", failure["preservation_error"])
        self.assertIn("TimeoutExpired", failure["primary_error"])
        self.assertEqual(stat.S_IMODE(diagnostic.stat().st_mode), 0o600)
        commands = json.loads((receipts / "1-commands.json").read_text())
        self.assertIsNone(commands[0]["exit_code"])
        self.assertFalse((receipts / "completion.json").exists())
        self.assertFalse((self.out / "preparation.json").exists())

    def test_deleted_input_without_primary_error_fails_preservation(self):
        def delete_after_build(*args, **kwargs):
            (self.root / "GNUmakefile").unlink()
            return {}

        self.out.mkdir()
        with patch.object(self.ci, "build_mode", side_effect=delete_after_build):
            with self.assertRaises(FileNotFoundError):
                self.ci.build(
                    self.root,
                    self.out / "receipts",
                    REV,
                    self.ci.environment(),
                    (1,),
                    self.out,
                )
        failure = json.loads(
            (self.out / "receipts/preservation-failure.json").read_text()
        )
        self.assertIsNone(failure["primary_error"])

    def test_final_selector_failure_never_publishes_preparation(self):
        self.ci.verify_selection.side_effect = RuntimeError("selector rejected")
        with self.assertRaisesRegex(RuntimeError, "selector rejected"):
            self.prepare()
        self.assertTrue((self.out / "system-gcc13/1-manifest.json").exists())
        self.assertFalse((self.out / "source-selection.json").exists())
        self.assertFalse((self.out / "preparation.json").exists())

    def test_local_shell_fails_closed_before_preparation(self):
        docs = (
            (ROOT / "docs/quality-control.md")
            .read_text()
            .split("## Local equivalents", 1)[1]
        )
        commands = docs.split("```", 2)[1].splitlines()[1:]
        self.assertEqual(commands[0], "set -euo pipefail")

    def test_compiler_mismatch_keeps_truth_and_stops_before_make(self):
        self.compiler = "cc unsupported actual compiler\n"
        with self.assertRaisesRegex(RuntimeError, "compiler"):
            self.prepare()
        self.assertFalse(any(a[0] == "/usr/bin/make" for a, _ in self.calls))
        self.assertIn(
            self.compiler,
            (self.out / "old-on/preflight.json").read_text().replace("\\n", "\n"),
        )

    def test_revision_validation_precedes_git_and_output_creation(self):
        for revision in (REV[:12], REV.upper(), REV + "\n"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.ci.prepare(self.root, self.out, revision)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.out.exists())

    def test_dirty_shallow_index_flags_and_local_overrides_block_build(self):
        for field, value in (
            ("dirty", " M GNUmakefile"),
            ("shallow", "true"),
            ("index", "h GNUmakefile\0"),
        ):
            with self.subTest(field=field):
                prior = getattr(self, field)
                setattr(self, field, value)
                with self.assertRaises(RuntimeError):
                    self.prepare()
                setattr(self, field, prior)
        (self.root / "local.mk").symlink_to(self.base / "missing")
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertFalse(any(a[0] == "/usr/bin/make" for a, _ in self.calls))

    def test_existing_symlink_or_nested_output_rejected(self):
        self.out.mkdir()
        sentinel = self.out / "do-not-touch"
        sentinel.write_text("preserve")
        with self.assertRaises((ValueError, FileExistsError)):
            self.prepare()
        self.assertEqual(sentinel.read_text(), "preserve")
        link = self.base / "link"
        link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.ci.prepare(self.root, link / "new", REV)
        with self.assertRaises(ValueError):
            self.ci.prepare(self.root, self.root / "output", REV)

    def test_measured_unit_receipts_match_unchanged_verifier_schema(self):
        from native_build_identity import verify_source_build

        self.prepare()

        def observed_git(root, *args):
            return self.ci.git(root, *args)

        with patch("native_build_identity._git", side_effect=observed_git):
            verified = verify_source_build(self.out / "system-gcc13", self.root, REV)
        self.assertEqual(verified.revision, REV)
        self.assertEqual(verified.metadata["header_count"], 1)
        self.assertEqual(verified.metadata["object_count"], 1)
        self.assertEqual(
            verified.artifact_hashes["dnethack"],
            self.ci.digest(self.root / "dnethackdir/dnethack"),
        )

    def test_suite_mask_preserves_public_negative_fixture_and_private_log(self):
        workflow = (ROOT / ".github/workflows/quality.yml").read_text()
        block = workflow.split(
            "      - name: Run the complete offline suite once\n", 1
        )[1]
        block = block.split("      - name: Retain selected", 1)[0]
        docs = (ROOT / "docs/quality-control.md").read_text()
        docs = docs.split('cd "$root"\n', 1)[1].split("```", 1)[0]
        for label, commands in (("workflow", block), ("docs", docs)):
            with self.subTest(label=label):
                before_env = commands.split("env -i", 1)[0]
                masks = re.findall(r"(?m)^\s*umask ([0-7]{3,4})\s*$", before_env)
                self.assertTrue(masks)
                prior = os.umask(int(masks[-1], 8))
                try:
                    public = self.base / (label + "-public")
                    public.mkdir(mode=0o755)
                finally:
                    os.umask(prior)
                self.assertEqual(stat.S_IMODE(public.stat().st_mode), 0o755)
                self.assertIn(': > "$out/full-suite.log"', before_env)
                self.assertLess(
                    before_env.index("umask 077"),
                    before_env.index(': > "$out/full-suite.log"'),
                )
                self.assertLess(
                    before_env.index(': > "$out/full-suite.log"'),
                    before_env.index("umask 022"),
                )

    def test_workflow_full_discovery_private_environment_and_receipts(self):
        text = (ROOT / ".github/workflows/quality.yml").read_text()
        job = text.split("  game:\n", 1)[1].split("  secrets:\n", 1)[0]
        for expected in (
            "fetch-depth: 0",
            "persist-credentials: false",
            "prepare_native_ci.py",
            '--expected-revision "$GITHUB_SHA"',
            "NYARLATHACK_PRECURIO_DIR=",
            "NYARLATHACK_NATIVE_FIXTURE_MODE=source-build",
            "NYARLATHACK_NATIVE_BUILD_RECEIPT=",
            "NYARLATHACK_NATIVE_EXPECTED_REVISION=",
            "PYTHONDONTWRITEBYTECODE=1",
            'TMPDIR="$out/fixtures"',
            'MAIL="$out/MAIL"',
            "env -i",
            "full-suite.log",
            "**/*.raw",
            "**/*.json",
            "retention-days: 7",
            "if: always()",
        ):
            self.assertIn(expected, job)
        self.assertEqual(
            job.count("-m unittest discover -s tests/chaos -p 'test_*.py' -v"), 1
        )
        self.assertNotIn("--retry", job)


class NativeCallerWiringTests(unittest.TestCase):
    """Source wiring and stdlib allocation units, not native acceptance."""

    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/quality.yml").read_text()
        self.game = self.workflow.split("  game:\n", 1)[1].split("  secrets:\n", 1)[0]
        self.suite = self.game.split(
            "      - name: Run the complete offline suite once\n", 1
        )[1].split("      - name: Retain selected", 1)[0]
        self.local = (
            (ROOT / "docs/quality-control.md")
            .read_text()
            .split("## Local equivalents", 1)[1]
            .split("```", 2)[1]
        )

    def test_exact_platform_and_whistle_environment_in_both_callers(self):
        expected = {
            "PLATFORM_ROOT": "$root",
            "PLATFORM_RECEIPT": "$out/system-gcc13",
            "PLATFORM_REVISION": "$revision",
            "PLATFORM_ARTIFACTS": "$invocation/platform",
            "PLATFORM_OFF_TUPLE": "$out/stock",
            "WHISTLE_ROOT": "$root",
            "WHISTLE_RECEIPT": "$out/system-gcc13",
            "WHISTLE_REVISION": "$revision",
            "WHISTLE_ARTIFACTS": "$invocation/whistle",
        }
        for label, source in (("CI", self.suite), ("local", self.local)):
            with self.subTest(caller=label):
                command = source.split("env -i", 1)[1]
                assignments = re.findall(
                    r'NYARLATHACK_((?:PLATFORM|WHISTLE)_[A-Z_]+)="([^"]+)"',
                    command,
                )
                self.assertEqual(len(assignments), 9)
                self.assertEqual(dict(assignments), expected)
                for assignment in (
                    'NYARLATHACK_STOCK_DIR="$out/stock"',
                    'NYARLATHACK_PRECURIO_DIR="$out/precurio"',
                    "NYARLATHACK_NATIVE_FIXTURE_MODE=source-build",
                    'NYARLATHACK_NATIVE_BUILD_RECEIPT="$out/system-gcc13"',
                    'NYARLATHACK_NATIVE_EXPECTED_REVISION="$revision"',
                    'HOME="$out/home"',
                    'MAIL="$out/MAIL"',
                    'TMPDIR="$out/fixtures"',
                ):
                    self.assertIn(assignment, command)
                self.assertNotIn("NYARLATHACK_OBSERVATIONS", source)
                self.assertEqual(command.count("-m unittest discover"), 1)
                self.assertNotIn("--retry", source)

    def test_private_absent_output_published_before_preparation(self):
        preparation = self.game.split(
            "      - name: Prepare authenticated native tuples\n", 1
        )[1].split("      - name: Run the complete", 1)[0]
        allocation = "container=$(mktemp -d /tmp/nyarl-native-ci.XXXXXX)"
        publish = 'printf \'NYARLATHACK_CI_OUT=%s\\n\' "$out" >> "$GITHUB_ENV"'
        for source in (preparation, self.local):
            with self.subTest(source=source[:40]):
                self.assertIn(allocation, source)
                self.assertLess(source.index("umask 077"), source.index(allocation))
                self.assertIn('out="$container/output"', source)
                self.assertIn('--output-dir "$out"', source)
                self.assertNotRegex(source, r"\b(?:mkdir|rm|ln)\b")
        self.assertIn(publish, preparation)
        self.assertLess(
            preparation.index(publish), preparation.index("/usr/bin/python3")
        )
        self.assertIn('--root "$GITHUB_WORKSPACE"', preparation)
        self.assertIn('--expected-revision "$GITHUB_SHA"', preparation)
        self.assertIn('out="$NYARLATHACK_CI_OUT"', self.suite)
        self.assertIn('root="$GITHUB_WORKSPACE"', self.suite)
        self.assertIn('revision="$GITHUB_SHA"', self.suite)
        self.assertIn('cd "$GITHUB_WORKSPACE"', self.suite)
        self.assertIn('cd "$root"', self.local)
        self.assertIn("revision=REVIEWED_REV\n", self.local)
        self.assertNotIn("rev-parse", self.local)
        self.assertNotIn("timeout-minutes: 0", self.game)
        self.assertIn("timeout-minutes: 15", self.game)

    def test_invocation_allocation_is_private_unique_with_absent_leaves(self):
        allocation = 'invocation=$(mktemp -d "$out/fixtures/full-suite.XXXXXX")'
        for source in (self.suite, self.local.split('cd "$root"', 1)[1]):
            self.assertIn(allocation, source)
            self.assertLess(source.index("umask 077"), source.index(allocation))
            self.assertLess(source.index(allocation), source.index("umask 022"))
            self.assertLess(source.index("umask 022"), source.index("env -i"))
            self.assertNotRegex(source, r"\b(?:mkdir|rm|ln)\b")
        # Unit-only analogue of two launches; never create/reuse artifact leaves.
        with tempfile.TemporaryDirectory(prefix="caller-unit-", dir="/tmp") as base:
            fixtures = Path(base) / "fixtures"
            fixtures.mkdir(mode=0o700)
            parents = [
                Path(tempfile.mkdtemp(prefix="full-suite.", dir=fixtures))
                for _ in range(2)
            ]
            leaves = [p / name for p in parents for name in ("platform", "whistle")]
            self.assertEqual(len(set(parents)), 2)
            self.assertEqual(len(set(leaves)), 4)
            for parent in parents:
                self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o700)
            self.assertTrue(all(not leaf.exists() for leaf in leaves))

    def upload_steps(self):
        # Deliberately narrow source parser; no PyYAML dependency in CI tests.
        blocks = re.split(r"(?m)^      - ", self.game)[1:]
        uploads = []
        for block in blocks:
            if "uses: actions/upload-artifact@" not in block:
                continue
            condition = re.findall(r"(?m)^        if: (.+)$", block)
            self.assertEqual(len(condition), 1, block)
            paths = re.search(
                r"(?m)^          path: \|\n((?:            .+\n)+)", block
            )
            self.assertIsNotNone(paths, block)
            name = re.findall(r"(?m)^          name: (.+)$", block)
            self.assertEqual(len(name), 1, block)
            uploads.append((name[0], condition[0], paths[1].splitlines(), block))
        self.assertTrue(uploads)
        return uploads

    def selected_uploads(self, env, previous_success):
        """Unit model of only these source conditions, not a hosted runner."""
        self.assertIsInstance(previous_success, bool)
        selected = {}
        for name, condition, paths, _ in self.upload_steps():
            # always() ignores the previous step's success/failure.
            if condition in ("always()", "${{ always() }}"):
                invoke = True
            elif condition == "${{ always() && env.NYARLATHACK_CI_OUT != '' }}":
                invoke = env.get("NYARLATHACK_CI_OUT", "") != ""
            else:
                self.fail("unsupported upload condition: " + condition)
            if not invoke:
                continue  # No dynamic path interpolation for a skipped action.
            self.assertNotIn(name, selected)
            selected[name] = [
                line.strip()
                .replace("${{ runner.temp }}", "/tmp/runner-unit")
                .replace(
                    "${{ env.NYARLATHACK_CI_OUT }}",
                    env.get("NYARLATHACK_CI_OUT", ""),
                )
                for line in paths
            ]
        return selected

    def test_preparation_log_upload_is_always_separate_from_dynamic_paths(self):
        uploads = self.upload_steps()
        self.assertEqual(len(uploads), 2)
        preparation = next(u for u in uploads if u[0] == "native-preparation-log")
        self.assertEqual(preparation[1], "always()")
        self.assertEqual(
            [line.strip() for line in preparation[2]],
            ["${{ runner.temp }}/native-preparation.log"],
        )
        self.assertNotIn("NYARLATHACK_CI_OUT", preparation[3])
        for _, _, _, block in uploads:
            self.assertIn(
                "uses: actions/upload-artifact@"
                "ea165f8d65b6e75b540449e92b4886f43607fa02 # v4",
                block,
            )
            self.assertIn("          if-no-files-found: ignore\n", block)
            self.assertIn("          retention-days: 7\n", block)

    def test_before_publication_missing_or_empty_output_skips_dynamic_upload(self):
        # Checkout, dependency, or allocation failure: no published output.
        # These are string-only selections; never expand filesystem globs.
        for env in ({}, {"NYARLATHACK_CI_OUT": ""}):
            for previous_success in (False, True):
                with self.subTest(env=env, previous_success=previous_success):
                    self.assertEqual(
                        self.selected_uploads(env, previous_success),
                        {
                            "native-preparation-log": [
                                "/tmp/runner-unit/native-preparation.log"
                            ]
                        },
                    )

    def test_after_publication_failed_preparer_retains_selected_private_paths(self):
        # Published before the preparer runs; failure must not suppress logs.
        out = "/tmp/nyarl-native-ci.UNIT/output"
        for previous_success in (False, True):
            with self.subTest(previous_success=previous_success):
                selected = self.selected_uploads(
                    {"NYARLATHACK_CI_OUT": out}, previous_success
                )
                self.assertEqual(
                    set(selected),
                    {"native-preparation-log", "native-build-and-test-logs"},
                )
                self.assertEqual(
                    selected["native-preparation-log"],
                    ["/tmp/runner-unit/native-preparation.log"],
                )
                paths = selected["native-build-and-test-logs"]
                self.assertTrue(paths)
                self.assertTrue(all(p.lstrip("!").startswith(out + "/") for p in paths))
                self.assertIn(out + "/old-on/*.log", paths)
                self.assertIn(out + "/system-gcc13/*.json", paths)
                self.assertIn("!" + out + "/fixtures/**/.git/**", paths)

    def test_upload_dynamic_base_selects_diagnostics_not_whole_tree(self):
        upload = next(
            u for u in self.upload_steps() if u[0] == "native-build-and-test-logs"
        )
        guard = "${{ always() && env.NYARLATHACK_CI_OUT != '' }}"
        self.assertEqual(upload[1], guard)
        self.assertLess(upload[3].index("if: " + guard), upload[3].index("uses:"))
        self.assertLess(upload[3].index("if: " + guard), upload[3].index("path: |"))
        paths = [line.strip() for line in upload[2]]
        base = "${{ env.NYARLATHACK_CI_OUT }}"
        expected = {
            base + "/*.json",
            base + "/full-suite.log",
            "!" + base + "/fixtures/**/.git/**",
        }
        expected.update(
            f"{base}/{folder}/*.{suffix}"
            for folder in ("system-gcc13", "old-on")
            for suffix in ("json", "log", "txt")
        )
        expected.update(
            f"{base}/{folder}/*-date.h" for folder in ("system-gcc13", "old-on")
        )
        expected.update(
            f"{base}/fixtures/**/*.{suffix}"
            for suffix in (
                "json",
                "jsonl",
                "raw",
                "log",
                "txt",
                "stdout",
                "stderr",
                "bin",
            )
        )
        self.assertEqual(set(paths), expected)
        self.assertEqual(len(paths), len(expected))
        self.assertIn("if-no-files-found: ignore", upload[3])
        self.assertIn("retention-days: 7", upload[3])
        self.assertNotIn("$RUNNER_TEMP/native-ci", self.game)

    def test_readme_keeps_offline_default_and_links_native_recipe(self):
        readme = (ROOT / "README.md").read_text()
        verification = readme.split("## Verification", 1)[1].split("## ", 1)[0]
        self.assertIn(
            "python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v",
            verification,
        )
        self.assertNotIn("NYARLATHACK_GAME_TESTS=1", verification)
        self.assertIn("docs/quality-control.md#local-equivalents", verification)


# These programs are Python-only. The recipe and its writer stay in the exact
# new session created by the runner; only the isolated harness is a subreaper.
RECIPE = r"""
import os, pathlib, signal, subprocess, sys
root = pathlib.Path(sys.argv[1])
(root / 'leader').write_text(str(os.getpid()))
signal.signal(signal.SIGTERM, signal.SIG_IGN)
signal.signal(signal.SIGUSR1, lambda *_: sys.exit(0))
child = subprocess.Popen([sys.executable, '-c', sys.argv[3], str(root)])
if sys.argv[2] == 'normal':
    child.wait()  # writer tells us to exit only after its readiness handshake
else:
    signal.pause()
"""
WRITER = r"""
import os, pathlib, signal, socket, sys
root = pathlib.Path(sys.argv[1])
signal.signal(signal.SIGTERM, signal.SIG_IGN)
with socket.socket(socket.AF_UNIX) as conn:
    conn.connect(str(root / 'ready.sock'))
    print('initial write', flush=True)
    conn.sendall((str(os.getpid()) + '\n').encode())
    while data := conn.recv(1):
        if data == b'e':
            os.kill(os.getppid(), signal.SIGUSR1)
        else:
            print('late write', flush=True)
            conn.sendall(b'w')
"""


def supervision_case(mode):
    """Run out of process so subreaping/signals cannot affect other tests."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # Linux PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "subreaper setup failed")
    spec = importlib.util.spec_from_file_location("ci_builder_real", SCRIPT)
    ci = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ci)
    with tempfile.TemporaryDirectory(prefix="native-ci-process-") as directory:
        root = Path(directory)
        receipts = root / "receipts"
        receipts.mkdir()
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(root / "ready.sock"))
        listener.listen(1)
        listener.settimeout(5)
        ready = threading.Event()
        peer = []
        thread_errors = []

        def baseline_term(signum, frame):
            # Also keep RED teardown reachable with the old unsupervised code.
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, baseline_term)
        previous = {
            sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)
        }

        def handshake():
            try:
                conn, _ = listener.accept()
                conn.settimeout(5)
                pid = int(conn.recv(64).strip())
                peer.append((conn, pid))
                ready.set()
                if mode == "normal":
                    conn.sendall(b"e")
                elif mode in ("sigint", "sigterm"):
                    os.kill(
                        os.getpid(),
                        signal.SIGINT if mode == "sigint" else signal.SIGTERM,
                    )
            except BaseException as exc:
                thread_errors.append(repr(exc))

        thread = threading.Thread(target=handshake, daemon=True)
        thread.start()
        real_run = subprocess.run
        runner = getattr(ci, "_run_build", None)
        if mode == "inspection-error":

            def unreadable_group(pgid):
                raise OSError("fixture proc read failure")

            ci._group_running = unreadable_group
        argv = [sys.executable, "-c", RECIPE, str(root), mode, WRITER]

        def run_recipe(unused_argv, **kwargs):
            if unused_argv[2] == "install":
                raise RuntimeError("fixture reached install")
            kwargs["timeout"] = 2
            if runner is None:
                # RED uses the actual old build_mode/subprocess.run path, with
                # argv/deadline substitution and a session solely for teardown.
                return real_run(argv, start_new_session=True, **kwargs)
            return runner(argv, **kwargs)

        result = {}
        started = time.monotonic()
        try:
            seam = "_run_build" if runner is not None else "subprocess"
            replacement = (
                run_recipe
                if runner is not None
                else type(
                    "OldRunner",
                    (),
                    {"run": staticmethod(run_recipe), "STDOUT": subprocess.STDOUT},
                )
            )
            with patch.object(ci, seam, replacement):
                try:
                    ci.build_mode(root, receipts, REV, {"PATH": "/usr/bin:/bin"}, 1)
                except BaseException as exc:
                    result["exception"] = type(exc).__name__
                    result["message"] = str(exc)
            thread.join(timeout=5)
            result["ready"] = ready.is_set()
            result["thread_errors"] = thread_errors
            result["elapsed"] = time.monotonic() - started
            result["handlers_restored"] = all(
                signal.getsignal(s) == h for s, h in previous.items()
            )
            leader = int((root / "leader").read_text())
            try:
                os.waitpid(leader, os.WNOHANG)
                result["leader_reaped"] = False
            except ChildProcessError:
                result["leader_reaped"] = True
            conn, pid = peer[0]
            try:
                state = (
                    Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                )
            except FileNotFoundError:
                state = "absent"
            result["descendant_state"] = state
            result["running_descendant"] = state not in ("absent", "Z", "X")
            before = (receipts / "1-clean.log").read_bytes()
            try:
                conn.sendall(b"w")
                reply = conn.recv(1)
            except (BrokenPipeError, ConnectionResetError):
                reply = b""
            result["late_write_ack"] = bool(reply)
            result["log_stable"] = before == (receipts / "1-clean.log").read_bytes()
            result["commands"] = json.loads((receipts / "1-commands.json").read_text())
        finally:
            # Retain only this invocation's leader/group. Reap our adopted
            # descendants even on RED; production does not claim to reap them.
            if (root / "leader").exists():
                leader = int((root / "leader").read_text())
                try:
                    os.killpg(leader, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + 3
                while True:
                    try:
                        reaped, _ = os.waitpid(-leader, os.WNOHANG)
                    except ChildProcessError:
                        result["fixture_reaped"] = True
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("fixture group did not reap within 3s")
                    if not reaped:
                        time.sleep(0.01)
            for conn, _ in peer:
                conn.close()
            listener.close()
            thread.join(timeout=6)
        return result


@unittest.skipUnless(sys.platform == "linux", "Linux process-group regression")
class BuildProcessSupervisionTests(unittest.TestCase):
    def check_case(self, mode):
        # No NativeCIPreparationTests mocks exist in this process or harness.
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--supervision-case", mode],
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        result = json.loads(completed.stdout)
        self.assertTrue(result["ready"], result)
        self.assertEqual(result["thread_errors"], [], result)
        self.assertTrue(result["fixture_reaped"], result)
        self.assertTrue(result["leader_reaped"], result)
        self.assertFalse(result["running_descendant"], result)
        self.assertFalse(result["late_write_ack"], result)
        self.assertTrue(result["log_stable"], result)
        self.assertTrue(result["handlers_restored"], result)
        self.assertLess(result["elapsed"], 10, result)
        return result

    def test_proc_inspection_error_still_kills_and_reaps_direct_child(self):
        result = self.check_case("inspection-error")
        self.assertEqual(result["exception"], "TimeoutExpired")
        self.assertIsNone(result["commands"][0]["exit_code"])

    def test_normal_exit_stops_remaining_writer_before_next_command(self):
        result = self.check_case("normal")
        self.assertEqual(result["commands"][0]["exit_code"], 0)
        self.assertEqual(result["message"], "fixture reached install")

    def test_keyboard_interrupt_stops_descendants_and_preserves_null_exit(self):
        result = self.check_case("sigint")
        self.assertEqual(result["exception"], "KeyboardInterrupt")
        self.assertIsNone(result["commands"][0]["exit_code"])

    def test_sigterm_stops_descendants_and_preserves_null_exit(self):
        result = self.check_case("sigterm")
        self.assertEqual(result["exception"], "SystemExit")
        self.assertEqual(result["message"], "143")
        self.assertIsNone(result["commands"][0]["exit_code"])

    def test_timeout_stops_term_ignoring_descendant_before_receipt(self):
        result = self.check_case("timeout")
        self.assertEqual(result["exception"], "TimeoutExpired")
        self.assertIsNone(result["commands"][0]["exit_code"])


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--supervision-case":
        print(json.dumps(supervision_case(sys.argv[2])))
    else:
        unittest.main()
