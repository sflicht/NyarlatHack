"""LINKED-NATIVE controlled author -> W/F composition, NOT ordinary play.

The author history/origin cache is a synthetic fixture, as in the older unit
and linked tests. Effects, presentation delivery, and hunger are native. No
provider, seed search, replay/save completion, or ordinary-route import.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

from chaos import next_use_author as author
from native_rng import controlled_rng_objects
from test_episodes import action, enabled, session, wire
from test_next_use_offline_author import fixture_sources, response

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/chaos/next_use_author_composition.c"


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NativeAuthorCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(
            tempfile.mkdtemp(prefix=".chaos-build-author-compose-", dir=ROOT)
        )
        print("NEXT_USE_AUTHOR_COMPOSITION_ARTIFACTS=" + str(cls.root), flush=True)
        cls.exe = cls.root / "composition"
        cls.validator = None

    def build(self):
        # Missing behavior is a test failure, not a compiler error or a skip.
        self.assertTrue(
            FIXTURE.exists(), "linked native author composition fixture missing"
        )
        if self.validator is not None:
            return
        flags = subprocess.check_output(
            ["/usr/bin/pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        library = self.root / "author.so"
        commands = [
            [
                "/usr/bin/cc",
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-misleading-indentation",
                "-std=c99",
                "-Wl,-z,defs",
                "-I" + str(ROOT / "include"),
                str(ROOT / "src/chaos_next_use.c"),
                str(ROOT / "src/chaos_lua.c"),
                str(ROOT / "tests/chaos/next_use_author_native.c"),
                *flags,
                "-lm",
                "-o",
                str(library),
            ],
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(self.root / "unixmain.o"),
            ],
        ]
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, timeout=45)
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                self.root / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        objects = controlled_rng_objects(objects, self.root)
        command = [
            "/usr/bin/cc",
            "-g",
            "-DCHAOS",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-unused-function",
            "-Wno-unused-variable",
            "-Wno-comment",
            "-I" + str(ROOT / "include"),
            str(FIXTURE),
            *map(str, objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *flags,
            "-o",
            str(self.exe),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        (self.root / "build.txt").write_text(result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        type(self).validator = author.NativeAuthorValidator(library)

    def run_case(self, program, mode):
        self.build()
        folder = Path(
            tempfile.mkdtemp(prefix=program + "-" + mode + "-", dir=self.root)
        )
        # Deliberately synthetic eligible history; never mislabel as ordinary play.
        rows = [enabled(), session(2)]
        origins = [
            action(rows, "whistling", "sound_high"),
            action(rows, "fountain_drink", "water_refreshed"),
        ]
        for row in rows:
            row.update(sanity=60, budget=6)
        schedule = [
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
            for family, origin in zip(("W", "F"), origins)
        ]
        for name, raw in (
            ("events.jsonl", wire(*rows)),
            ("next_use-schedule.jsonl", wire(*schedule)),
        ):
            with os.fdopen(
                os.open(folder / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
                "wb",
            ) as out:
                out.write(raw)
        source = fixture_sources()[0 if program == "state" else 1]
        transport = author.FakeAuthorTransport(response(source))
        receipt = author.author_offline(
            folder, transport=transport, validator=self.validator
        )
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(receipt["validation"], "native_parser_and_load")
        self.assertEqual(receipt["native_admission"], "unverified")
        envelope = json.loads((folder / "next_use-envelope.json").read_bytes())
        self.assertEqual(envelope["source"].encode(), source)
        self.assertEqual(envelope["source_sha256"], hashlib.sha256(source).hexdigest())
        self.assertEqual(envelope["operations"], ["W", "F"])
        self.assertEqual(
            (envelope["cost"], envelope["ttl"], envelope["telegraph"]),
            (2, 100, "next-use-v2-WF"),
        )
        evidence = {p.name: p.read_bytes() for p in folder.glob("next_use-*")}
        env = dict(os.environ, TERM="xterm", COLUMNS="80", LINES="24")
        result = subprocess.run(
            [str(self.exe), mode, str(folder)],
            cwd=folder,
            env=env,
            input=b" " * 4096,
            capture_output=True,
            timeout=15,
        )
        (folder / "native.stdout").write_bytes(result.stdout)
        (folder / "native.stderr").write_bytes(result.stderr)
        self.assertEqual(result.returncode, 0, (folder, result.stderr))
        for name, raw in evidence.items():
            current = (folder / name).read_bytes()
            if name == "next_use-schedule.jsonl":
                # Native delivered F completion appends its genuine new origin.
                self.assertTrue(current.startswith(raw), name)
            else:
                self.assertEqual(current, raw, name)
        row = json.loads((folder / "result.json").read_bytes())
        event_bytes = (folder / "events.jsonl").read_bytes()
        self.assertTrue(event_bytes.startswith(wire(*rows)), "history prefix changed")
        events = [json.loads(line) for line in event_bytes.splitlines()]
        # Native suffix only: synthetic origins cannot satisfy these assertions.
        row["events"] = events[len(rows) :]
        row["folder"] = str(folder)
        self.assertEqual((row["admitted"], row["spent"], row["telegraph"]), (1, 2, 1))
        self.assertEqual(row["source_sha256"], receipt["source_sha256"])
        self.assertEqual(row["envelope_sha256"], receipt["envelope_sha256"])
        self.assertEqual(
            row["fate_probe"], 14
        )  # Existing native_rng.h seed 123; no search.
        return row

    def assert_witness(self, row):
        self.assertEqual((row["ready_before"], row["ready_after"]), (1, 0))
        self.assertEqual((row["displaced"], row["delivered"], row["public"]), (1, 1, 1))
        self.assertNotEqual((row["ox"], row["oy"]), (row["mx"], row["my"]))
        public = row["public_record"]
        self.assertEqual((public["family"], public["phase"]), (1, 1))
        observations = {
            e["seq"]: e["observation"] for e in row["events"] if "observation" in e
        }
        self.assertLess(public["root"], public["notice_seq"])
        self.assertLess(public["notice_seq"], public["end_seq"])
        root = observations[public["root"]]
        self.assertEqual(
            (root["operation"], root["stage"], root["root_seq"]),
            ("whistle_attention", "started", 0),
        )
        for key, stage, fact in (
            ("notice_seq", "notice", "attention"),
            ("end_seq", "completed", "none"),
        ):
            observation = observations[public[key]]
            self.assertEqual(
                (
                    observation["operation"],
                    observation["stage"],
                    observation["root_seq"],
                    observation["fact"],
                ),
                ("whistle_attention", stage, public["root"], fact),
            )

    def assert_refresh(self, row):
        self.assertGreater(row["hunger_after"], row["hunger_before"])
        self.assertEqual(
            (row["contacted"], row["remap_before"], row["token_active_after"]),
            (1, 1, 0),
        )
        self.assertEqual((row["slot_f"], row["f_effect"]), (2, 12))
        self.assertTrue(
            any(
                e.get("observation", {}).get("fact") == "water_refreshed"
                for e in row["events"]
            )
        )

    def assert_quiet(self, row):
        self.assertEqual(
            (row["remap_before"], row["token_active_after"], row["slot_f"]), (0, 0, 4)
        )
        self.assertEqual(row["hunger_after"], row["hunger_before"])
        self.assertFalse(
            any(
                e.get("observation", {}).get("fact") == "water_refreshed"
                for e in row["events"]
            )
        )

    def test_state_program_native_refresh_before_w_but_quiet_after_w(self):
        before = self.run_case("state", "f_first")
        after = self.run_case("state", "delivered")
        self.assert_refresh(before)
        self.assertEqual(before["state"], 0)
        self.assert_witness(after)
        self.assert_quiet(after)
        self.assertEqual(after["state"], 1)

    def test_witness_program_requires_real_delivery_despite_native_displacement(self):
        delivered = self.run_case("witness", "delivered")
        lost = self.run_case("witness", "undelivered")
        self.assert_witness(delivered)
        # Corrupt only a copied diagnostic; retained native evidence is untouched.
        for key in ("notice_seq", "end_seq"):
            malformed = copy.deepcopy(delivered)
            for event in malformed["events"]:
                if event["seq"] == malformed["public_record"][key]:
                    event["observation"]["root_seq"] = 0
            with self.assertRaises(AssertionError):
                self.assert_witness(malformed)
        self.assert_refresh(delivered)
        self.assertEqual(delivered["state"], 1)
        self.assertEqual(
            (lost["ready_before"], lost["ready_after"], lost["classifier"]), (1, 0, 1)
        )
        self.assertEqual(
            (lost["displaced"], lost["delivered"], lost["public"]), (1, 0, 0)
        )
        self.assertEqual((lost["mx"], lost["my"]), (delivered["mx"], delivered["my"]))
        self.assertEqual(lost["dog_rng_draws"], delivered["dog_rng_draws"])
        self.assert_quiet(lost)
        self.assertEqual(lost["state"], 0)
        with self.assertRaises(AssertionError):
            self.assert_witness(lost)
        with self.assertRaises(AssertionError):
            self.assert_refresh(lost)

    def test_w_native_effect_bypass_fails_positive_oracle(self):
        bypass = self.run_case("witness", "w_bypass")
        self.assertEqual((bypass["ready_before"], bypass["ready_after"]), (1, 1))
        self.assertEqual(bypass["public"], 0)
        self.assert_quiet(bypass)
        with self.assertRaises(AssertionError):
            self.assert_witness(bypass)

    def test_f_native_effect_bypass_is_not_a_refresh_receipt(self):
        bypass = self.run_case("witness", "f_bypass")
        self.assert_witness(bypass)
        self.assertEqual(
            (bypass["contacted"], bypass["remap_before"], bypass["token_active_after"]),
            (1, 1, 1),
        )
        self.assertEqual(bypass["hunger_after"], bypass["hunger_before"])
        self.assertEqual(bypass["f_effect"], 0)
        with self.assertRaises(AssertionError):
            self.assert_refresh(bypass)

    def test_native_rng_oracles_reject_actual_extra_draws(self):
        self.build()
        for mode, oracle in (
            ("--rng-negative-control", "reseed_count == 0"),
            ("--raw-rng-negative-control", "rn2(100000) == expected"),
        ):
            result = subprocess.run(
                [str(self.exe), mode], capture_output=True, text=True, timeout=15
            )
            (self.root / (mode[2:] + ".txt")).write_text(result.stdout + result.stderr)
            self.assertEqual(result.returncode, -signal.SIGABRT)
            self.assertIn(oracle, result.stderr)
