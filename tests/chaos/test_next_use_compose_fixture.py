"""Two handwritten next-use programs over the same native adapters.

These are fixtures, not a claim about model authorship or ordinary play.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseComposeFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nyarl-compose-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "compose"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        result = subprocess.run(
            [
                "/usr/bin/gcc",
                "-DCHAOS",
                "-ffunction-sections",
                "-fdata-sections",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-Wno-misleading-indentation",
                "-isystem",
                str(ROOT / "include"),
                str(ROOT / "tests/chaos/next_use_compose_fixture.c"),
                str(ROOT / "src/chaos_next_use.c"),
                str(ROOT / "src/chaos_next_use_admission.c"),
                str(ROOT / "src/chaos_next_use_runtime.c"),
                str(ROOT / "src/chaos_protocol.c"),
                str(ROOT / "src/chaos_lua.c"),
                "-Wl,--gc-sections",
                "-lm",
                *flags,
                "-o",
                str(cls.exe),
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_mode(self, mode):
        result = subprocess.run(
            [str(self.exe), mode], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_state_program_refreshes_before_attention_and_stays_quiet_after(self):
        first = self.run_mode("state_f_first")
        later = self.run_mode("state_after_w")
        self.assertEqual(first["acted"], 1)
        self.assertEqual(first["remap"], 1)
        self.assertEqual(first["effect"], 12)
        self.assertEqual(later["acted"], 0)
        self.assertEqual(later["remap"], 0)
        self.assertEqual(later["state"], 1)
        self.assertEqual(later["slot_f"], 4)
        self.assertEqual(later["effect"], 0)
        self.assertEqual(later["w_runtime"], 1)

    def test_witness_program_refreshes_only_after_delivered_manifestation(self):
        delivered = self.run_mode("witness_delivered")
        undelivered = self.run_mode("witness_undelivered")
        self.assertEqual(delivered["public"], 1)
        self.assertEqual(delivered["acted"], 1)
        self.assertEqual(delivered["remap"], 1)
        self.assertEqual(delivered["effect"], 12)
        self.assertEqual(delivered["slot_f"], 2)
        self.assertEqual(undelivered["public"], 0)
        self.assertEqual(undelivered["acted"], 0)
        self.assertEqual(undelivered["remap"], 0)
        self.assertEqual(undelivered["slot_f"], 4)
        self.assertEqual(undelivered["effect"], 0)
        self.assertEqual(undelivered["w_runtime"], 1)
