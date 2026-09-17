"""Build-free SYNTHETIC tests for the existing selected-action native adapter."""

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
DRIVER = HERE / "test_episode_action_transport.py"
PREFIX = "NYARLATHACK_ACTION_TRANSPORT_"


class ActionTransportAdapterUnitTests(unittest.TestCase):
    def load(self, enabled="1"):
        with mock.patch.dict(
            os.environ, {"NYARLATHACK_GAME_TESTS": enabled}, clear=enabled != "1"
        ):
            spec = importlib.util.spec_from_file_location(
                "transport_adapter_unit", DRIVER
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def values(self, parent):
        return {
            PREFIX + "ROOT": str(HERE.parents[1]),
            PREFIX + "RECEIPT": str(parent / "missing-receipt"),
            PREFIX + "REVISION": "a" * 40,
            PREFIX + "ARTIFACTS": str(parent / "transport"),
        }

    def run_suite(self, enabled="1"):
        suite = unittest.defaultTestLoader.loadTestsFromModule(self.load(enabled))
        self.assertEqual(suite.countTestCases(), 1, "exactly one native registration")
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.testsRun, 1)
        return result

    def test_import_is_inert_and_optin_skip_is_honest(self):
        with mock.patch.object(native_driver_supervision, "run_driver") as run:
            for enabled in ("", "0", "yes"):
                result = self.run_suite(enabled)
                self.assertEqual(len(result.skipped), 1)
                self.assertIn("native opt-in", result.skipped[0][1])
            run.assert_not_called()

    def test_synthetic_success_passes_exact_selection_to_outer_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.values(Path(tmp))
            with (
                mock.patch.dict(os.environ, values, clear=True),
                mock.patch.object(
                    native_driver_supervision, "run_driver", return_value=(0, Path(tmp))
                ) as run,
            ):
                result = self.run_suite()
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
            self.assertFalse(result.skipped)
            args = []
            for key in ("ROOT", "RECEIPT", "REVISION", "ARTIFACTS"):
                args.extend(["--" + key.lower(), values[PREFIX + key]])
            run.assert_called_once_with(
                DRIVER, args, values[PREFIX + "ROOT"], values[PREFIX + "ARTIFACTS"]
            )

    def test_synthetic_nonzero_exit_propagates(self):
        with tempfile.TemporaryDirectory() as tmp:
            for code in (1, 9, 124, 125):
                with (
                    self.subTest(code=code),
                    mock.patch.dict(os.environ, self.values(Path(tmp)), clear=True),
                    mock.patch.object(
                        native_driver_supervision,
                        "run_driver",
                        return_value=(code, Path(tmp)),
                    ),
                ):
                    result = self.run_suite()
                self.assertEqual(len(result.failures), 1)
                self.assertFalse(result.skipped)
                self.assertIn(tmp, result.failures[0][1])

    def test_missing_configuration_fails_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.values(Path(tmp))
            for key in values:
                env = dict(values)
                del env[key]
                with (
                    self.subTest(key=key),
                    mock.patch.dict(os.environ, env, clear=True),
                    mock.patch.object(native_driver_supervision, "run_driver") as run,
                ):
                    result = self.run_suite()
                    self.assertEqual(len(result.failures), 1)
                    self.assertIn(key, result.failures[0][1])
                    run.assert_not_called()

    def test_bad_receipt_fails_real_preflight_without_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with mock.patch.dict(os.environ, self.values(parent), clear=True):
                result = self.run_suite()
            self.assertEqual(len(result.failures), 1, result.errors)
            self.assertFalse((parent / "transport").exists())
            logs = list(parent.glob("transport.driver-*"))
            self.assertEqual(len(logs), 1)
            self.assertIn(
                "invalid receipt directory", (logs[0] / "driver.stderr").read_text()
            )

    def test_optimized_adapter_and_cli_fail_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(
                os.environ,
                **self.values(Path(tmp)),
                NYARLATHACK_GAME_TESTS="1",
                PYTHONDONTWRITEBYTECODE="1",
            )
            for command in (
                ["-m", "unittest", "test_episode_action_transport"],
                [str(DRIVER)],
            ):
                p = subprocess.run(
                    [sys.executable, "-O", *command],
                    cwd=HERE,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("optimized Python is not supported", p.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_ci_wires_existing_adapter_without_duplicate_native_launch(self):
        workflow = (HERE.parents[1] / ".github/workflows/quality.yml").read_text()
        self.assertIn("scripts/run_native_tests.py", workflow)
        self.assertIn('--build-output "$out"', workflow)
        self.assertNotIn(PREFIX + "ROOT=", workflow)
        self.assertIn("scripts/run_native_tests.py", workflow)
        self.assertNotIn("test_episode_action_transport.py", workflow)
        self.assertIn("${{ always() && env.NYARLATHACK_CI_OUT != '' }}", workflow)


if __name__ == "__main__":
    unittest.main()
