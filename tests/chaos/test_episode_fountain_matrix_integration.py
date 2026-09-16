"""Strict native matrix registration; adapter unit tests are SYNTHETIC only."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import native_driver_supervision

HERE = Path(__file__).resolve().parent
DRIVER = HERE / "test_episode_fountain_matrix.py"
PREFIX = "NYARLATHACK_FOUNTAIN_"
ARTIFACTS = "NYARLATHACK_FOUNTAIN_MATRIX_ARTIFACTS"


def run_native(test):
    if not __debug__ or sys.flags.optimize or os.environ.get("PYTHONOPTIMIZE"):
        raise RuntimeError("optimized Python is not supported")
    args = []
    for key in ("ROOT", "RECEIPT", "REVISION"):
        value = os.environ.get(PREFIX + key)
        test.assertTrue(value, "explicit " + PREFIX + key + " required")
        args.extend(["--" + key.lower(), value])
    out = os.environ.get(ARTIFACTS)
    test.assertTrue(out, "explicit " + ARTIFACTS + " required")
    args.extend(["--artifacts", out])
    root = os.environ[PREFIX + "ROOT"]
    code, logs = native_driver_supervision.run_driver(DRIVER, args, root, out)
    test.assertEqual(code, 0, f"matrix driver failed ({code}); diagnostics: {logs}")
    # Fresh interpreter: oracle import-time evidence cannot be stale discovery state.
    code, logs = native_driver_supervision.run_driver(
        Path(__file__).resolve(),
        ["--oracle-evidence", out, "--oracle-receipt", out + "/oracle-execution.json"],
        root,
        out + ".oracle",
    )
    test.assertEqual(code, 0, f"matrix oracle failed ({code}); diagnostics: {logs}")


@unittest.skipUnless(os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "native opt-in")
class FountainMatrixNativeTests(unittest.TestCase):
    def test_fresh_matrix_and_all_artifact_oracles(self):
        run_native(self)


def oracle_main(argv):
    """Bounded child entry point; not another native driver or fallback oracle."""
    import argparse

    if not __debug__ or sys.flags.optimize or os.environ.get("PYTHONOPTIMIZE"):
        raise RuntimeError("optimized Python is not supported")
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-evidence", required=True)
    parser.add_argument("--oracle-receipt", required=True)
    args = parser.parse_args(argv)
    evidence = str(Path(args.oracle_evidence).resolve(strict=True))
    os.environ["FOUNTAIN_MATRIX_EVIDENCE"] = evidence
    os.environ["FOUNTAIN_MATRIX_CONTROL_EVIDENCE"] = evidence
    sys.path.insert(0, str(HERE.parents[1]))
    sys.path.insert(0, str(HERE))
    import test_episode_fountain_matrix_oracle as oracle

    names = unittest.defaultTestLoader.getTestCaseNames(oracle.MatrixOracleTests)
    expected = {
        "test_pair_rejects_each_state_domain",
        "test_actual_history_mutations",
        "test_optimization_rejected_before_work",
        "test_budget_control_rejects_unrelated_player_mutation",
        "test_special_manifest_is_finite_and_explicit",
        "test_actual_special_pairs_and_history_mutations",
        "test_manifest_requires_all_actual_fates",
    }
    if set(names) != expected:
        raise RuntimeError(
            "matrix oracle discovery must contain all seven reviewed methods"
        )
    executed = []

    class RecordingResult(unittest.TextTestResult):
        def startTest(self, test):
            executed.append(test.id())
            super().startTest(test)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(oracle.MatrixOracleTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(
        suite
    )
    passed = result.wasSuccessful() and result.testsRun == 7 and not result.skipped
    receipt = {
        "scope": "artifact-dependent oracle execution, not a fresh production build",
        "FOUNTAIN_MATRIX_EVIDENCE": evidence,
        "FOUNTAIN_MATRIX_CONTROL_EVIDENCE": evidence,
        "oracle_module": str(Path(oracle.__file__).resolve()),
        "testsRun": result.testsRun,
        "executed": executed,
        "skipped": result.skipped,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "passed": passed,
    }
    with Path(args.oracle_receipt).open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    return 0 if passed else 1


class MatrixAdapterUnitTests(unittest.TestCase):
    """Build-free orchestration checks, never native acceptance."""

    def values(self, parent):
        return {
            PREFIX + "ROOT": str(HERE.parents[1]),
            PREFIX + "RECEIPT": str(parent / "missing-receipt"),
            PREFIX + "REVISION": "a" * 40,
            ARTIFACTS: str(parent / "matrix"),
        }

    def invoke(self):
        self.assertTrue(
            callable(globals().get("run_native")), "native registration missing"
        )
        run_native(self)

    def test_synthetic_success_routes_matrix_then_explicit_oracles(self):
        with tempfile.TemporaryDirectory() as tmp:
            values = self.values(Path(tmp))
            with (
                mock.patch.dict(os.environ, values),
                mock.patch.object(
                    native_driver_supervision, "run_driver", return_value=(0, Path(tmp))
                ) as run,
            ):
                self.invoke()
            self.assertEqual(run.call_count, 2)
            first, second = run.call_args_list
            self.assertEqual(first.args[0], DRIVER)
            self.assertEqual(first.args[2], values[PREFIX + "ROOT"])
            self.assertEqual(first.args[3], values[ARTIFACTS])
            self.assertEqual(second.args[0], Path(__file__).resolve())
            self.assertEqual(
                second.args[1],
                [
                    "--oracle-evidence",
                    values[ARTIFACTS],
                    "--oracle-receipt",
                    values[ARTIFACTS] + "/oracle-execution.json",
                ],
            )
            self.assertNotEqual(first.args[3], second.args[3])

    def test_synthetic_nonzero_propagates_and_blocks_oracles(self):
        with tempfile.TemporaryDirectory() as tmp:
            for code in (1, 9, 124, 125):
                with (
                    self.subTest(code=code),
                    mock.patch.dict(os.environ, self.values(Path(tmp))),
                    mock.patch.object(
                        native_driver_supervision,
                        "run_driver",
                        return_value=(code, Path(tmp)),
                    ) as run,
                ):
                    with self.assertRaisesRegex(
                        AssertionError, f"driver failed \\({code}\\)"
                    ):
                        self.invoke()
                    self.assertEqual(run.call_count, 1)

    def test_synthetic_oracle_failure_is_not_native_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.dict(os.environ, self.values(Path(tmp))),
                mock.patch.object(
                    native_driver_supervision,
                    "run_driver",
                    side_effect=[(0, Path(tmp)), (1, Path(tmp))],
                ),
            ):
                with self.assertRaisesRegex(AssertionError, "oracle failed"):
                    self.invoke()

    def test_missing_or_empty_configuration_fails_before_launch(self):
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
                        with self.assertRaisesRegex(AssertionError, key):
                            self.invoke()
                        run.assert_not_called()

    def test_bad_receipt_fails_real_preflight_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with mock.patch.dict(os.environ, self.values(parent)):
                with self.assertRaisesRegex(AssertionError, "driver failed"):
                    self.invoke()
            self.assertFalse((parent / "matrix").exists())
            logs = list(parent.glob("matrix.driver-*"))
            self.assertEqual(len(logs), 1)
            self.assertIn(
                "invalid receipt directory", (logs[0] / "driver.stderr").read_text()
            )

    def test_discovery_registers_one_native_test_and_optin_is_honest(self):
        for enabled in ("", "0", "yes"):
            env = dict(
                os.environ, NYARLATHACK_GAME_TESTS=enabled, PYTHONDONTWRITEBYTECODE="1"
            )
            p = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "unittest",
                    "test_episode_fountain_matrix_integration.FountainMatrixNativeTests",
                    "-v",
                ],
                cwd=HERE,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("Ran 1 test", p.stderr)
            self.assertIn("skipped=1", p.stderr)
            self.assertIn("native opt-in", p.stderr)

    def test_optimized_native_adapter_fails_without_output(self):
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
                    "test_episode_fountain_matrix_integration.FountainMatrixNativeTests",
                ],
                cwd=HERE,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("optimized Python", p.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_oracle_child_overrides_stale_evidence_and_never_skips_missing_artifacts(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp)
            receipt = evidence / "oracle-execution.json"
            env = dict(
                os.environ,
                FOUNTAIN_MATRIX_EVIDENCE="/stale/not-input",
                FOUNTAIN_MATRIX_CONTROL_EVIDENCE="/stale/not-input",
                PYTHONDONTWRITEBYTECODE="1",
            )
            p = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--oracle-evidence",
                    tmp,
                    "--oracle-receipt",
                    str(receipt),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertNotEqual(p.returncode, 0)
            record = json.loads(receipt.read_text())
            self.assertFalse(record["passed"])
            self.assertEqual(record["testsRun"], 7)
            self.assertEqual(len(set(record["executed"])), 7)
            self.assertEqual(record["skipped"], [])
            self.assertEqual(record["FOUNTAIN_MATRIX_EVIDENCE"], tmp)
            self.assertEqual(record["FOUNTAIN_MATRIX_CONTROL_EVIDENCE"], tmp)
            self.assertEqual(record["errors"], 4)

    def test_real_preflight_repeated_attempts_keep_unique_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            with mock.patch.dict(os.environ, self.values(parent)):
                for _ in range(2):
                    with self.assertRaisesRegex(AssertionError, "driver failed"):
                        self.invoke()
            logs = list(parent.glob("matrix.driver-*"))
            self.assertEqual(len(logs), 2)
            self.assertFalse((parent / "matrix").exists())
            for log in logs:
                self.assertEqual(log.stat().st_mode & 0o777, 0o700)
                self.assertEqual(
                    json.loads((log / "supervisor.status.json").read_text())[
                        "family_cleanup"
                    ],
                    "verified",
                )

    def test_ci_has_dedicated_absent_leaf_and_preserves_upload_guard(self):
        workflow = (HERE.parents[1] / ".github/workflows/quality.yml").read_text()
        self.assertIn(ARTIFACTS + '="$invocation/fountain-matrix"', workflow)
        self.assertIn("${{ always() && env.NYARLATHACK_CI_OUT != '' }}", workflow)
        self.assertNotIn("test_episode_fountain_matrix.py", workflow)


if __name__ == "__main__":
    if "--oracle-evidence" in sys.argv:
        sys.exit(oracle_main(sys.argv[1:]))
    unittest.main()
