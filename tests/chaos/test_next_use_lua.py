"""Characterization of next-use Lua load/on_action; real interpreter."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseLuaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nyarl-next-use-lua-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "next-use-lua"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        result = subprocess.run(
            [
                "cc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-std=c99",
                "-I" + str(ROOT / "include"),
                str(ROOT / "src/chaos_lua.c"),
                str(ROOT / "tests/chaos/next_use_lua.c"),
                *flags,
                "-o",
                str(cls.exe),
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_case(self, *args, stdin=None):
        p = subprocess.run(
            [str(self.exe), *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        rows = [json.loads(line) for line in p.stdout.splitlines() if line]
        return rows

    def test_load_and_on_action_quiet(self):
        load = self.run_case("load-quiet")[0]
        action = self.run_case("on-action-quiet")[0]
        self.assertEqual(load["status"], 0)
        self.assertEqual(action["status"], 0)
        self.assertEqual(action["op"], 0)
        self.assertEqual(action["state"], 0)

    def test_rejects_nul_and_oversize_source(self):
        self.assertNotEqual(self.run_case("load-nul")[0]["status"], 0)
        self.assertNotEqual(self.run_case("load-oversize")[0]["status"], 0)

    def test_rejects_extra_root_result(self):
        self.assertNotEqual(self.run_case("extra-root")[0]["status"], 0)

    def test_rejects_unknown_field_wrong_op_and_state(self):
        unknown = self.run_case("unknown-field")[0]
        bad_op = self.run_case("bad-op")[0]
        high = self.run_case("state-high")[0]
        two = self.run_case("two-returns")[0]
        for row in (unknown, bad_op, high, two):
            self.assertNotEqual(row["status"], 0)
            self.assertEqual(row["op"], 0)
            self.assertEqual(row["state"], 0)

    def test_instruction_limit_then_valid_call(self):
        rows = self.run_case("loop")
        self.assertEqual(rows[0]["status"], 2)  # SANDBOX_INSTRUCTION
        self.assertEqual(rows[0]["op"], 0)
        self.assertEqual(rows[1]["recovery"], 0)
        self.assertEqual(rows[1]["op"], 0)

    def test_context_does_not_expose_fate(self):
        row = self.run_case("hidden-fate")[0]
        self.assertEqual(row["status"], 0)
        self.assertEqual(row["op"], 0)

    def test_upvalue_does_not_persist_across_fresh_calls(self):
        first, second = self.run_case("upvalue-counter")
        self.assertEqual(first["status"], 0)
        self.assertEqual(second["status"], 0)
        self.assertEqual(first["state"], 1)
        self.assertEqual(second["state"], 1)

    def test_returned_state_can_drive_a_later_call(self):
        first, second = self.run_case("returned-state")
        self.assertEqual(first["status"], 0)
        self.assertEqual(first["state"], 1)
        self.assertEqual(second["status"], 0)
        self.assertEqual(second["state"], 2)
