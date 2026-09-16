"""Portable test-harness regressions; no native games or historical claims."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("test_episode_turnloop_provenance.py")
ENV_KEYS = tuple(
    "NYARLATHACK_TURNLOOP_STOCK_" + suffix
    for suffix in ("TUPLE", "RECEIPT", "REVISION")
)
HISTORICAL = "IntegrationTests.test_historical_fixed_evidence_mutations"


class PortabilityTests(unittest.TestCase):
    def run_child(self, configuration, *selection):
        env = os.environ.copy()
        for key in (*ENV_KEYS, "PYTHONPATH", "PYTHONOPTIMIZE"):
            env.pop(key, None)
        env.update(configuration)
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *selection, "-v"],
            cwd=SCRIPT.parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_default_unit_suite_has_one_explicit_artifact_skip(self):
        result = self.run_child({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ran 8 tests", result.stderr)
        self.assertIn("OK (skipped=1)", result.stderr)
        self.assertIn("historical evidence not configured", result.stderr)
        self.assertNotIn("/home/", SCRIPT.read_text())

    def test_partial_configuration_fails_closed(self):
        for key in ENV_KEYS:
            with self.subTest(key=key):
                result = self.run_child({key: "configured"}, HISTORICAL)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    "incomplete historical evidence configuration", result.stderr
                )
                self.assertNotIn("skipped", result.stderr)

    def test_missing_configured_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_child(
                dict(
                    zip(
                        ENV_KEYS,
                        (
                            str(Path(tmp) / "missing-tuple"),
                            str(Path(tmp) / "missing-receipt"),
                            "1" * 40,
                        ),
                    )
                ),
                HISTORICAL,
            )
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn("FileNotFoundError", result.stderr)
        self.assertNotIn("skipped", result.stderr)

    def test_corrupt_configured_inputs_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = root / "manifest.json"
            receipt.write_bytes(b"corrupt UNIT input, not historical evidence")
            dump = root / "game/dumplog/1700000000"
            dump.parent.mkdir(parents=True)
            dump.write_bytes(b"corrupt")
            for name in ("dnethack", "nhdat", "license"):
                (root / name).write_bytes(b"corrupt")
            result = self.run_child(
                dict(
                    zip(
                        ENV_KEYS,
                        (
                            str(root),
                            str(receipt),
                            "1" * 40,
                        ),
                    )
                ),
                HISTORICAL,
            )
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn("ValueError", result.stderr)
        self.assertNotIn("skipped", result.stderr)


if __name__ == "__main__":
    unittest.main()
