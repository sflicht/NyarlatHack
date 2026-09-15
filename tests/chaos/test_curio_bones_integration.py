"""Whole native bones publication/readback; controlled wizard level, not TTY."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import unittest

from gameplay_support import ROOT

COMPRESSION_MACROS = (
    "COMPRESS",
    "COMPRESS_EXTENSION",
    "INTERNAL_COMP",
    "ZEROCOMP",
    "RLECOMP",
)
SOURCE_MARKERS = (b"TASK6D_DEAD_SOURCE_ONLY", b"TASK6D_LIVE_SOURCE_ONLY")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_payload(test, payload):
    """Only the verified no-compression build is supported, never auto-decode."""
    test.assertTrue(payload, "empty native publication")
    test.assertFalse(payload.startswith(b"\x1f\x8b"), "unexpected gzip encoding")
    for marker in SOURCE_MARKERS:
        test.assertNotIn(marker, payload, "player source marker leaked into bones")


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class CurioBonesIntegrationTests(unittest.TestCase):
    def test_whole_bones(self):
        artifacts = Path(
            os.environ.get("CURIO_BONES_INTEGRATION_ARTIFACTS")
            or tempfile.mkdtemp(prefix="nyarl-curio-bones-integration-")
        )
        artifacts.mkdir(parents=True, exist_ok=True)
        print(f"CURIO_BONES_INTEGRATION_ARTIFACTS={artifacts}", flush=True)
        source = ROOT / "tests/chaos/curio_bones_integration.c"
        self.assertTrue(source.is_file(), "missing whole-bones native fixture")
        self.assertEqual((ROOT / ".chaos-build").read_text().strip(), "1")
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / p
                for p in (
                    "sys/unix/unixres.o",
                    "sys/unix/unixunix.o",
                    "sys/unix/unixmain.o",
                    "sys/share/ioctl.o",
                    "sys/share/unixtty.o",
                )
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        tracked = (
            subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
            .decode()
            .split("\0")
        )
        protected = set(objects) | {
            ROOT / p for p in tracked if Path(p).suffix in (".c", ".h", ".py")
        }
        protected.update(
            ROOT / p
            for p in (
                "GNUmakefile",
                ".chaos-build",
                "dnethackdir/dnethack",
                "dnethackdir/nhdat",
            )
        )
        # Include generated/ignored headers and the two untracked test sources.
        protected.update((ROOT / "include").rglob("*.h"))
        protected.update((source, Path(__file__).resolve()))
        if (ROOT / "local.mk").exists():
            protected.add(ROOT / "local.mk")
        protected = sorted(protected)
        before = {str(p): digest(p) for p in protected}
        (artifacts / "inputs-before.json").write_text(json.dumps(before, indent=2))
        evidence = {
            "protected_inputs_count": len(before),
            "encoding": "native-uncompressed",
            "alternate_compression": "unsupported/unexercised",
        }

        def verify_inputs():
            after = {str(p): digest(p) for p in protected}
            (artifacts / "inputs-after.json").write_text(json.dumps(after, indent=2))
            self.assertEqual(before, after)

        self.addCleanup(verify_inputs)
        macro_command = [
            "cc",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            "-dM",
            "-E",
            "-include",
            "hack.h",
            "-x",
            "c",
            "/dev/null",
        ]
        macros = subprocess.check_output(macro_command, text=True)
        (artifacts / "active-macros.txt").write_text(macros)
        defined = set(re.findall(r"^#define (\w+)", macros, re.M))
        evidence["compression_macros"] = {
            name: name in defined for name in COMPRESSION_MACROS
        }
        evidence["preprocessor_command"] = macro_command
        self.assertFalse(
            defined.intersection(COMPRESSION_MACROS),
            "unsupported compression configuration; do not infer native object mode from headers",
        )

        def check_noop_functions(path, label):
            # Bounded to this approved x86-64 build, not a general disassembler.
            # Both original object and linked fixture must retain the verified
            # stack-only no-op bodies; alternate builds fail, never silently skip.
            for symbol in ("compress", "uncompress"):
                command = [
                    "objdump",
                    "-d",
                    "--no-show-raw-insn",
                    "--disassemble=" + symbol,
                    str(path),
                ]
                body = subprocess.check_output(command, text=True)
                (artifacts / f"{label}-{symbol}.txt").write_text(body)
                ops = [
                    " ".join(line.split())
                    for line in re.findall(r"^\s*[0-9a-f]+:[ \t]+([^\n]+)", body, re.M)
                ]
                self.assertEqual(
                    ops,
                    [
                        "endbr64",
                        "push %rbp",
                        "mov %rsp,%rbp",
                        "mov %rdi,-0x8(%rbp)",
                        "nop",
                        "pop %rbp",
                        "ret",
                    ],
                    "unsupported native compression body; inspect object evidence",
                )

        check_noop_functions(ROOT / "src/files.o", "native-object")
        for relative, options in (
            ("sys/unix/unixmain.o", ["--redefine-sym=main=original_game_main"]),
            ("src/invent.o", ["--globalize-symbol=nextgetobj"]),
            (
                "src/restore.o",
                ["--globalize-symbol=loadfruitchn", "--globalize-symbol=freefruitchn"],
            ),
        ):
            original = ROOT / relative
            exposed = artifacts / original.name
            subprocess.run(
                ["objcopy", *options, str(original), str(exposed)], check=True
            )
            objects = [exposed if p == original else p for p in objects]
        exe = artifacts / "curio-bones-integration"
        command = [
            "cc",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-isystem",
            str(ROOT / "include"),
            str(source),
            *map(str, objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ]
        (artifacts / "build-command.txt").write_text(repr(command))
        linked_before = {str(p): digest(p) for p in objects}
        (artifacts / "linked-inputs-before.json").write_text(
            json.dumps(linked_before, indent=2)
        )
        subprocess.run(command, check=True, timeout=45)
        check_noop_functions(exe, "linked-fixture")
        game = artifacts / "game"
        # Never archive/reuse an earlier run's state. Request a fresh directory.
        self.assertFalse(
            game.exists(),
            "artifact game already exists; use a fresh artifact directory",
        )
        game.mkdir()
        for name in ("nhdat", "license"):
            shutil.copy2(ROOT / "dnethackdir" / name, game / name)

        evidence["runs"] = {}

        def run(mode, directory=game, label=None, failure=None):
            label = label or mode
            p = subprocess.run(
                [str(exe), mode], cwd=directory, capture_output=True, timeout=30
            )
            log = p.stdout + p.stderr
            (artifacts / f"{label}.log").write_bytes(log)
            evidence["runs"][label] = {
                "returncode": p.returncode,
                "mode": mode,
                "cwd": str(directory),
            }
            if failure is None:
                self.assertEqual(p.returncode, 0, log)
                self.assertIn(b"compiled-format: native-uncompressed", log)
            else:
                self.assertEqual(p.returncode, -signal.SIGABRT, log)
                self.assertIn(failure, log)
            return log

        run("publish")
        files = list(game.glob("bon*"))
        self.assertEqual(len(files), 1)
        bone = files[0]
        self.assertNotEqual(bone.suffix, ".gz")
        payload = bone.read_bytes()
        assert_payload(self, payload)
        (artifacts / "published.bones").write_bytes(payload)
        evidence.update(
            bones_path=str(bone),
            published_sha256=digest(bone),
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            payload_bytes=len(payload),
            native_header_prefix_hex=payload[:32].hex(),
        )
        for mode in ("observe", "consume"):
            log = run(mode)
            if mode == "observe":
                fields = re.search(rb"native-version: (\d+) (\d+) (\d+) (\d+)", log)
                self.assertIsNotNone(fields)
                assert fields is not None
                evidence["native_version_fields"] = dict(
                    zip(
                        ("incarnation", "feature_set", "entity_count", "struct_sizes"),
                        map(int, fields.groups()),
                    )
                )
            self.assertEqual(bone.read_bytes(), payload)

        def isolated(label):
            target = artifacts / label
            shutil.copytree(game, target)
            return target

        # Actual native whole-file tag corruption, never the positive artifact.
        legacy = isolated("negative-legacy")
        run("legacy-file", legacy)
        legacy_payload = (legacy / bone.name).read_bytes()
        self.assertNotEqual(legacy_payload, payload)
        run("observe", legacy, "reject-legacy-tag", b"o->curio_tag==")
        # Actual getbones(TRUE) must demote the hostile tag, unlike the observer.
        run("consume", legacy, "accept-demoted-legacy-tag")
        self.assertEqual((legacy / bone.name).read_bytes(), legacy_payload)
        broken_header = isolated("negative-header")
        (broken_header / bone.name).write_bytes(bytes([payload[0] ^ 255]) + payload[1:])
        run("observe", broken_header, "reject-native-header", b'uptodate(fd,"bones")')
        for mode, assertion in (
            ("bad-record", b"!memcmp(&saved,&u.curio,sizeof saved)"),
            ("bad-output", b'!strcmp(output,"This curio is inert.'),
        ):
            run(mode, isolated(mode), failure=assertion)
        # Assertion sensitivity, not a claim that the engine leaks source:
        # append each marker to isolated whole-file bytes and use SAME validator.
        evidence["payload_negative_controls"] = []
        for index, marker in enumerate(SOURCE_MARKERS):
            corrupt = artifacts / f"negative-source-{index}.bones"
            corrupt.write_bytes(payload + marker)
            with self.assertRaisesRegex(AssertionError, "player source marker leaked"):
                assert_payload(self, corrupt.read_bytes())
            evidence["payload_negative_controls"].append(marker.decode())
        with self.assertRaisesRegex(AssertionError, "unexpected gzip encoding"):
            assert_payload(self, b"\x1f\x8b" + payload)
        self.assertEqual(bone.read_bytes(), payload)
        linked_after = {str(p): digest(p) for p in objects}
        (artifacts / "linked-inputs-after.json").write_text(
            json.dumps(linked_after, indent=2)
        )
        self.assertEqual(linked_before, linked_after)
        evidence.update(
            source_sha256=digest(source),
            python_sha256=digest(Path(__file__)),
            executable_sha256=digest(exe),
        )
        (artifacts / "evidence.json").write_text(json.dumps(evidence, indent=2))
