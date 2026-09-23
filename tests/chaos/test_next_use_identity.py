"""ENGINE-UNIT identity lifetime, not whole native restore acceptance."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseIdentityTests(unittest.TestCase):
    def test_distinct_games_in_same_birthday_second(self):
        with tempfile.TemporaryDirectory(prefix="nyarl-identity-") as tmp:
            binary = Path(tmp) / "identity"
            subprocess.run(
                [
                    "/usr/bin/cc",
                    "-DCHAOS",
                    "-ffunction-sections",
                    "-fdata-sections",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-isystem",
                    str(ROOT / "include"),
                    str(ROOT / "tests/chaos/next_use_identity.c"),
                    str(ROOT / "src/chaos_engine.c"),
                    "-Wl,--gc-sections",
                    "-o",
                    str(binary),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            result = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=5
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "positive": 1,
                    "stable": 1,
                    "distinct_same_second": 1,
                },
            )
