"""Real uncompressed whole-level bones; synthetic next-use bootstrap, not play."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from gameplay_support import ROOT, _install_asset
from test_curio_bones_integration import assert_payload, digest

DONOR = "return {on_action=function(c) return {next_use_intent_v=2,op='quiet',state=1} end} --NEXT_USE_BONES_DONOR"
RECEIVER = "return {on_action=function(c) return {next_use_intent_v=2,op='quiet',state=2} end} --NEXT_USE_BONES_RECEIVER"


def assert_no_next_use_payload(test, payload):
    assert_payload(test, payload)
    for source in (DONOR, RECEIVER):
        for marker in (
            source.encode(),
            source.split("--", 1)[1].encode(),
            hashlib.sha256(source.encode()).hexdigest().encode(),
        ):
            test.assertNotIn(
                marker, payload, "next-use source/identity leaked into bones"
            )
    test.assertNotIn(b"NUS1", payload, "next-use save extension leaked into bones")


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseBonesIntegrationTests(unittest.TestCase):
    def test_donor_does_not_replace_absent_or_owned_receiver(self):
        artifacts = Path(tempfile.mkdtemp(prefix="nyarl-next-use-bones-"))
        print(f"NEXT_USE_BONES_ARTIFACTS={artifacts}", flush=True)
        source = ROOT / "tests/chaos/next_use_bones_integration.c"
        self.assertTrue(source.is_file(), "missing next-use bones boundary fixture")
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
        protected = set(objects) | set((ROOT / "include").rglob("*.h"))
        protected.update(
            ROOT / p
            for p in subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
            .decode()
            .split("\0")
            if Path(p).suffix in (".c", ".h", ".py")
        )
        protected.update(
            (
                source,
                Path(__file__),
                ROOT / "GNUmakefile",
                ROOT / ".chaos-build",
                ROOT / "dnethackdir/dnethack",
                ROOT / "dnethackdir/nhdat",
            )
        )
        if (ROOT / "local.mk").exists():
            protected.add(ROOT / "local.mk")
        before = {str(p): digest(p) for p in sorted(protected)}
        (artifacts / "inputs-before.json").write_text(json.dumps(before, indent=2))

        def verify_inputs():
            after = {str(p): digest(p) for p in sorted(protected)}
            (artifacts / "inputs-after.json").write_text(json.dumps(after, indent=2))
            self.assertEqual(before, after)

        self.addCleanup(verify_inputs)
        commands = []
        evidence = {
            "scope": "controlled wizard whole savebones/getbones; synthetic next-use bootstrap",
            "encoding": "native-uncompressed",
            "compression_alternatives": "unsupported",
            "ordinary_play": False,
            "runs": {},
            "skips": 0,
        }
        self.addCleanup(
            lambda: (artifacts / "evidence.json").write_text(
                json.dumps(evidence, indent=2)
            )
        )
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
            command = ["objcopy", *options, str(original), str(exposed)]
            commands.append(command)
            subprocess.run(command, check=True, timeout=30)
            objects = [exposed if p == original else p for p in objects]
        exe = artifacts / "next-use-bones"
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
            "-Wl,--wrap=savebones",
            "-Wl,--wrap=getbones",
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ]
        commands.append(command)
        (artifacts / "build-commands.json").write_text(json.dumps(commands, indent=2))
        (artifacts / "compiled-inputs.json").write_text(
            json.dumps({str(p): digest(p) for p in objects}, indent=2)
        )
        for path in (
            source,
            Path(__file__),
            ROOT / "tests/chaos/curio_bones_integration.c",
        ):
            shutil.copy2(path, artifacts / path.name)
        built = subprocess.run(command, capture_output=True, timeout=60)
        (artifacts / "build.log").write_bytes(built.stdout + built.stderr)
        self.assertEqual(built.returncode, 0, built.stderr)
        evidence["executable_sha256"] = digest(exe)
        # Same explicit x86-64 uncompressed-build contract as the original
        # whole-curio test. Header guards alone cannot attest linked objects.
        for image, label in ((ROOT / "src/files.o", "native"), (exe, "linked")):
            for symbol in ("compress", "uncompress"):
                command = [
                    "objdump",
                    "-d",
                    "--no-show-raw-insn",
                    "--disassemble=" + symbol,
                    str(image),
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
                    "unsupported native compression body",
                )

        def case(name):
            directory = artifacts / name
            directory.mkdir()
            for asset in ("nhdat", "license"):
                _install_asset(
                    ROOT / "dnethackdir" / asset,
                    directory / asset,
                    artifacts / "assets",
                )
            return directory

        def run(mode, directory):
            result = subprocess.run(
                [str(exe), mode], cwd=directory, capture_output=True, timeout=30
            )
            log = result.stdout + result.stderr
            (directory / "native.log").write_bytes(log)
            evidence["runs"][mode] = {
                "returncode": result.returncode,
                "cwd": str(directory),
            }
            self.assertEqual(result.returncode, 0, log)
            return log

        donor = case("donor")
        run("publish", donor)
        bones = list(donor.glob("bon*"))
        self.assertEqual(len(bones), 1)
        bone = bones[0]
        payload = bone.read_bytes()
        (artifacts / "published.bones").write_bytes(payload)
        assert_no_next_use_payload(self, payload)
        evidence["bones_sha256"] = digest(bone)
        evidence["bones_bytes"] = len(payload)
        donor_state = json.loads((donor / "before.json").read_text())
        self.assertEqual(donor_state["source"], DONOR)
        self.assertEqual(donor_state["run_token"], 111)
        self.assertEqual(donor_state["state"], 1)
        self.assertEqual(donor_state["slot_f"], 1)
        self.assertEqual(donor_state["spent"], 2)
        for mode in ("absent", "owned"):
            receiver = case(mode)
            shutil.copy2(
                bone, receiver / bone.name
            )  # Only donor transfer: actual bones.
            log = run(mode, receiver)
            self.assertIn(b"consume: 59 objects; 43 inert/16 ordinary", log)
            self.assertIn(b"next-use: getbones=1; has_loaded_bones=1", log)
            before_state = json.loads((receiver / "before.json").read_text())
            after_state = json.loads((receiver / "after.json").read_text())
            self.assertEqual(
                before_state,
                after_state,
                "receiver next-use state inherited or changed",
            )
            self.assertEqual(before_state["monstermoves"], 200)
            self.assertEqual(before_state["player_token"], 222)
            self.assertEqual(
                before_state["source"], RECEIVER if mode == "owned" else ""
            )
            self.assertEqual(before_state["state"], 2 if mode == "owned" else 0)
            self.assertEqual(before_state["spent"], 2 if mode == "owned" else 0)
            self.assertEqual(before_state["attempted"], int(mode == "owned"))
            self.assertEqual(before_state["valid"], int(mode == "owned"))
            self.assertEqual(before_state["run_token"], 222 if mode == "owned" else 0)
            self.assertEqual(before_state["slot_f"], int(mode == "owned"))
            self.assertEqual(before_state["armed_m_id"], 0)
            self.assertEqual(before_state["attention_claimed"], 0)
            self.assertEqual(before_state["witnessed"], 0)
            self.assertEqual(before_state["public_count"], 0)
            self.assertEqual(before_state["private_count"], 3 if mode == "owned" else 0)
            self.assertEqual(before_state["receipt_count"], int(mode == "owned"))
            self.assertEqual(before_state["callback_ordinal"], int(mode == "owned"))
            self.assertEqual(before_state["player_attempted"], int(mode == "owned"))
            self.assertEqual(
                before_state["source_sha256"],
                hashlib.sha256(RECEIVER.encode()).hexdigest()
                if mode == "owned"
                else "",
            )
            self.assertEqual(
                before_state["admission_move"], 200 if mode == "owned" else 0
            )
            self.assertEqual(
                before_state["program_expiry"], 300 if mode == "owned" else 0
            )
            self.assertEqual(
                (receiver / "before.snapshot.bin").read_bytes(),
                (receiver / "after.snapshot.bin").read_bytes(),
            )
            self.assertEqual((receiver / bone.name).read_bytes(), payload)
        # Byte-leak sensitivity ONLY: not an executable-inheritance mutant.
        leaked = artifacts / "negative-appended-source.bones"
        leaked.write_bytes(payload + DONOR.encode())
        with self.assertRaisesRegex(
            AssertionError, "next-use source/identity leaked"
        ) as caught:
            assert_no_next_use_payload(self, leaked.read_bytes())
        (artifacts / "negative-byte-leak.log").write_text(str(caught.exception))
        evidence["negative_control"] = (
            "appended real donor source rejected by same byte oracle; not execution/inheritance"
        )
        self.assertEqual(bone.read_bytes(), payload)
