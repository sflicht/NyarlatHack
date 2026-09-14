"""Player-known vitals and native observation/cancelled-prayer evidence."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from chaos.director import State
from chaos.protocol import parse_event
from test_director import event

ROOT = Path(__file__).resolve().parents[2]
VITALS = dict(hp=7, hp_max=20, power=2, power_max=10)


class ObservationSchemaTests(unittest.TestCase):
    def test_vitals_whitelist_and_history(self):
        state = State()
        state.ingest(
            event(
                event="read",
                phase="attempt",
                detail="HIDDEN-IDENTITY",
                vitals=VITALS,
                otyp=999,
                inventory_id=123,
            )
        )
        summary = json.loads(state.summary())
        self.assertEqual(summary["observed"]["vitals"], VITALS)
        self.assertEqual(summary["recent"][0]["vitals"], VITALS)
        for hidden in ("HIDDEN-IDENTITY", "otyp", "inventory_id", "detail"):
            self.assertNotIn(hidden, state.summary())

    def test_reject_invalid_vitals(self):
        for values in (
            None,
            {},
            {**VITALS, "otyp": 999},
            {**VITALS, "hp": True},
            {**VITALS, "hp": -1},
            {**VITALS, "power": "secret"},
            {**VITALS, "hp_max": 2147483648},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                parse_event(json.dumps(event(vitals=values)).encode())
        self.assertEqual(
            parse_event(json.dumps(event(vitals={**VITALS, "power": -1})).encode())[
                "vitals"
            ]["power"],
            -1,
        )

    def test_prayer_disclosure_is_exact_and_old_logs_work(self):
        for detail, phase, expected in (
            ("confirmed", "attempt", "confirmed"),
            ("cancelled", "result", "cancelled"),
            ("HIDDEN-DIVINE-STATE", "result", None),
            ("confirmed", "result", None),
        ):
            state = State()
            state.ingest(event(event="pray", phase=phase, detail=detail))
            record = json.loads(state.summary())["recent"][0]
            self.assertEqual(record.get("prayer"), expected)
            self.assertNotIn("HIDDEN-DIVINE-STATE", state.summary())
        state = State()
        state.ingest(event())
        self.assertNotIn("vitals", json.loads(state.summary())["observed"])


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NativeObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="nyarl-observations-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        subprocess.run(
            [
                "objcopy",
                "--redefine-sym",
                "main=original_game_main",
                str(ROOT / "sys/unix/unixmain.o"),
                str(cls.root / "unixmain.o"),
            ],
            check=True,
            timeout=20,
        )
        objects = (
            sorted((ROOT / "src").glob("*.o"))
            + [
                ROOT / "sys/unix/unixres.o",
                ROOT / "sys/unix/unixunix.o",
                cls.root / "unixmain.o",
                ROOT / "sys/share/ioctl.o",
                ROOT / "sys/share/unixtty.o",
            ]
            + sorted((ROOT / "win/tty").glob("*.o"))
            + sorted((ROOT / "win/curses").glob("*.o"))
        )
        cls.exe = cls.root / "observations"
        subprocess.run(
            [
                "cc",
                "-g",
                "-DCHAOS",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/observations.c"),
                *map(str, objects),
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
        run = cls.root / "run"
        run.mkdir(mode=0o700)
        result = subprocess.run(
            [str(cls.exe)],
            env={**os.environ, "NYARLATHACK_RUN_DIR": str(run)},
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        cls.events = [
            parse_event(line)
            for line in (run / "events.jsonl").read_bytes().splitlines()
        ]

    def test_status_selection_and_clamp(self):
        by_name = {
            e["event"]: e for e in self.events if e["event"] in ("read", "apply", "zap")
        }
        self.assertEqual(by_name["read"]["vitals"], VITALS)
        self.assertEqual(
            by_name["apply"]["vitals"], dict(hp=3, hp_max=9, power=2, power_max=10)
        )
        self.assertEqual(
            by_name["zap"]["vitals"], dict(hp=0, hp_max=9, power=-1, power_max=10)
        )
        self.assertTrue(all(e["detail"] == "" for e in by_name.values()))

    def test_native_cancel_has_no_safe_point(self):
        prayers = [e for e in self.events if e["event"] == "pray"]
        self.assertEqual(
            [(e["phase"], e["detail"], e["safe"]) for e in prayers],
            [("result", "cancelled", 1)],
        )

    def test_coalesced_thresholds_in_both_directions(self):
        self.assertEqual(
            [
                (e["safe"], e["sanity"])
                for e in self.events
                if e["event"] == "safe_point"
            ],
            [(1, 100), (2, 40), (3, 100)],
        )
