"""Build-free SYNTHETIC adapter tests, not native acceptance evidence."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import native_driver_supervision

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "test_episode_fountain.py"
PREFIX = "NYARLATHACK_FOUNTAIN_"


class FountainIntegrationTests(unittest.TestCase):
    def load(self, enabled="1"):
        with mock.patch.dict(os.environ, {"NYARLATHACK_GAME_TESTS": enabled}):
            spec = importlib.util.spec_from_file_location(
                "fountain_adapter_unit", DRIVER
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def suite(self, module):
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        self.assertEqual(
            suite.countTestCases(), 1, "register exactly one native adapter"
        )
        return suite

    def values(self, root):
        return {
            PREFIX + "ROOT": str(HERE.parents[1]),
            PREFIX + "RECEIPT": str(root / "missing-receipt"),
            PREFIX + "REVISION": "a" * 40,
            PREFIX + "ARTIFACTS": str(root / "absent"),
        }

    def run_suite(self, module):
        result = unittest.TestResult()
        self.suite(module).run(result)
        return result

    def test_import_is_inert_and_disabled_discovery_skips(self):
        with mock.patch.object(native_driver_supervision, "run_driver") as run:
            for enabled in ("", "0", "yes"):
                with self.subTest(enabled=enabled):
                    result = self.run_suite(self.load(enabled))
                    self.assertEqual(result.testsRun, 1)
                    self.assertEqual(len(result.skipped), 1)
                    self.assertIn("opt-in", result.skipped[0][1])
            run.assert_not_called()

    def test_synthetic_success_routes_only_strict_oracle_to_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.values(Path(tmp))
            with (
                mock.patch.dict(os.environ, values),
                mock.patch.object(
                    native_driver_supervision, "run_driver", return_value=(0, Path(tmp))
                ) as run,
            ):
                result = self.run_suite(self.load())
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
            self.assertFalse(result.skipped)
            expected = []
            for key in ("ROOT", "RECEIPT", "REVISION", "ARTIFACTS"):
                expected.extend(["--" + key.lower(), values[PREFIX + key]])
            expected.extend(["--oracle", "strict-desired"])
            run.assert_called_once_with(
                DRIVER, expected, values[PREFIX + "ROOT"], values[PREFIX + "ARTIFACTS"]
            )

    def test_synthetic_nonzero_is_failure_with_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            for code in (1, 9, 124, 125):
                with (
                    self.subTest(code=code),
                    mock.patch.dict(os.environ, self.values(Path(tmp))),
                    mock.patch.object(
                        native_driver_supervision,
                        "run_driver",
                        return_value=(code, Path(tmp)),
                    ),
                ):
                    result = self.run_suite(self.load())
                    self.assertEqual(len(result.failures), 1)
                    self.assertFalse(result.skipped)
                    self.assertIn(f"driver failed ({code})", result.failures[0][1])
                    self.assertIn(tmp, result.failures[0][1])

    def test_missing_or_empty_selection_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.values(Path(tmp))
            for key in values:
                for empty in (False, True):
                    env = dict(values)
                    if empty:
                        env[key] = ""
                    else:
                        del env[key]
                    with (
                        self.subTest(key=key, empty=empty),
                        mock.patch.dict(os.environ, env, clear=True),
                        mock.patch.object(
                            native_driver_supervision, "run_driver"
                        ) as run,
                    ):
                        result = self.run_suite(self.load())
                        self.assertEqual(len(result.failures), 1)
                        self.assertIn(key, result.failures[0][1])
                        run.assert_not_called()

    def test_nonexistent_receipt_fails_real_preflight_without_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict(os.environ, self.values(root)):
                result = self.run_suite(self.load())
            self.assertEqual(len(result.failures), 1, result.errors)
            self.assertFalse(result.skipped)
            self.assertFalse((root / "absent").exists())
            logs = list(root.glob("absent.driver-*"))
            self.assertEqual(len(logs), 1)
            self.assertIn(
                "invalid receipt directory", (logs[0] / "driver.stderr").read_text()
            )

    def test_wrong_revision_fails_real_driver_without_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = self.values(root)
            values[PREFIX + "REVISION"] = "malformed-not-normalized"
            with mock.patch.dict(os.environ, values):
                result = self.run_suite(self.load())
            self.assertEqual(len(result.failures), 1, result.errors)
            logs = list(root.glob("absent.driver-*"))
            self.assertEqual(len(logs), 1)
            self.assertIn(
                "40hex revision required", (logs[0] / "driver.stderr").read_text()
            )
            self.assertFalse((root / "absent").exists())

    def test_optimized_discovery_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(
                os.environ,
                **self.values(Path(tmp)),
                NYARLATHACK_GAME_TESTS="1",
                PYTHONDONTWRITEBYTECODE="1",
            )
            p = subprocess.run(
                [
                    sys.executable,
                    "-O",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(HERE),
                    "-p",
                    DRIVER.name,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("optimized Python is not supported", p.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_optimized_cli_environment_guard_is_preserved(self):
        p = subprocess.run(
            [sys.executable, str(DRIVER)],
            env=dict(os.environ, PYTHONOPTIMIZE="1", PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("optimized Python is not supported", p.stderr)

    def test_ci_supplies_explicit_selection_without_duplicate_cli(self):
        workflow = (HERE.parents[1] / ".github/workflows/quality.yml").read_text()
        for key, value in (
            ("ROOT", "$root"),
            ("RECEIPT", "$out/system-gcc13"),
            ("REVISION", "$revision"),
            ("ARTIFACTS", "$invocation/fountain"),
        ):
            self.assertIn(f'{PREFIX}{key}="{value}"', workflow)
        self.assertIn("${{ always() && env.NYARLATHACK_CI_OUT != '' }}", workflow)
        self.assertIn("${{ env.NYARLATHACK_CI_OUT }}/fixtures/**/*.jsonl", workflow)
        self.assertNotIn("test_episode_fountain.py", workflow)


if __name__ == "__main__":
    unittest.main()
