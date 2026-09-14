import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ShadowTests(unittest.TestCase):
    def test_isolation_and_timeout(self):
        self.assertTrue((ROOT / "src/chaos_shadow.c").exists(), "shadow runner missing")
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "shadow"
            subprocess.run(
                [
                    "cc",
                    "-std=c99",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I" + str(ROOT / "include"),
                    str(ROOT / "src/chaos_shadow.c"),
                    str(ROOT / "tests/chaos/shadow_harness.c"),
                    "-o",
                    str(exe),
                ],
                check=True,
            )
            p = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
            self.assertEqual(p.stdout.strip(), "1 7 1 1 1")
            p = subprocess.run(
                [str(exe), "loop"], capture_output=True, text=True, timeout=5
            )
            self.assertTrue(p.stdout.startswith("0 7 "), p.stdout)
