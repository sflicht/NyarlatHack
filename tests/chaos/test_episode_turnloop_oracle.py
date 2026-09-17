"""Exact native turn-loop artifact comparison; no generated event fixtures."""

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class OptimizedDriverTests(unittest.TestCase):
    def test_optimized_entrypoints_reject_before_artifacts(self):
        driver = Path(__file__).with_name("test_episode_turnloop.py").resolve()
        modes = ((["-O"], None), (["-OO"], None), ([], "1"), ([], "2"))
        for flags, optimize in modes:
            for entrypoint in ("cli", "main"):
                for help_only in (True, False):
                    with self.subTest(
                        flags=flags, env=optimize, entrypoint=entrypoint, help=help_only
                    ):
                        with tempfile.TemporaryDirectory() as directory:
                            root = Path(directory)
                            artifacts = root / "artifacts"
                            args = (
                                ["--help"]
                                if help_only
                                else [
                                    "--root",
                                    str(root / "missing-root"),
                                    "--receipt",
                                    str(root / "missing-receipt"),
                                    "--revision",
                                    "1" * 40,
                                    "--off-tuple",
                                    str(root / "missing-tuple"),
                                    "--artifacts",
                                    str(artifacts),
                                ]
                            )
                            env = dict(os.environ)
                            env.pop("PYTHONOPTIMIZE", None)
                            env["PYTHONDONTWRITEBYTECODE"] = "1"
                            if optimize is not None:
                                env["PYTHONOPTIMIZE"] = optimize
                            command = [sys.executable, "-B", *flags]
                            if entrypoint == "cli":
                                command += [str(driver), *args]
                            else:
                                command += [
                                    "-c",
                                    (
                                        "import runpy, sys\n"
                                        "def reject_effect(event, args):\n"
                                        "    if event in ('os.mkdir', 'os.fork', 'os.forkpty', "
                                        "'os.exec', 'os.posix_spawn', 'os.system', "
                                        "'subprocess.Popen', 'shutil.copyfile'):\n"
                                        "        raise RuntimeError('unexpected side effect: ' + event)\n"
                                        "sys.addaudithook(reject_effect)\n"
                                        "sys.path.insert(0, sys.argv[1])\n"
                                        "module = runpy.run_path(sys.argv[2])\n"
                                        "module['main'](sys.argv[3:])"
                                    ),
                                    str(driver.parent),
                                    str(driver),
                                    *args,
                                ]
                            result = subprocess.run(
                                command,
                                env=env,
                                cwd=root,
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn(
                                "optimized Python is unsupported", result.stderr
                            )
                            self.assertNotIn("TURNLOOP_ARTIFACTS=", result.stdout)
                            self.assertNotIn("NATIVE_VARIANT=", result.stdout)
                            self.assertEqual(list(root.iterdir()), [])

    def test_actual_interpreter_flags_not_mutable_environment(self):
        driver = Path(__file__).with_name("test_episode_turnloop.py").resolve()
        env = dict(os.environ, PYTHONOPTIMIZE="2", PYTHONDONTWRITEBYTECODE="1")
        # -E ignores startup env; setting it after startup cannot remove asserts.
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-E",
                "-c",
                "import os, runpy, sys; "
                "sys.path.insert(0, sys.argv[1]); "
                "module = runpy.run_path(sys.argv[2]); "
                "os.environ['PYTHONOPTIMIZE'] = '2'; "
                "module['main'](['--help'])",
                str(driver.parent),
                str(driver),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_quit_is_not_an_assertion_side_effect(self):
        tree = ast.parse(
            Path(__file__).with_name("test_episode_turnloop.py").read_text()
        )
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "quit"
        ]
        self.assertEqual(len(calls), 1)
        assertion_calls = [
            node
            for assertion in ast.walk(tree)
            if isinstance(assertion, ast.Assert)
            for node in ast.walk(assertion)
            if isinstance(node, ast.Call)
        ]
        self.assertNotIn(calls[0], assertion_calls)


def read_native(directory):
    directory = Path(directory)
    return {
        "inputs": json.loads((directory / "inputs.json").read_text()),
        "terminal": (directory / "terminal.raw").read_bytes(),
        "xlog": (directory / "game/xlogfile").read_bytes(),
        "dumps": {
            p.name: p.read_bytes().hex()
            for p in (directory / "game/dumplog").iterdir()
            if p.is_file()
        },
    }


def compare_runs(reference, candidate):
    """No terminal, input, score, or final-dump normalization is permitted."""
    for key in ("inputs", "terminal", "xlog", "dumps"):
        assert reference[key] == candidate[key], key + " parity"


def legacy_projection(raw):
    """Remove only v2 rows and the consequent shared sequence renumbering."""
    rows = [json.loads(line) for line in raw.splitlines()]
    result = []
    for row in rows:
        if row["v"] == 1:
            row = dict(row)
            row["seq"] = len(result) + 1
            result.append(row)
    return result


class TurnloopOracleTests(unittest.TestCase):
    def test_empty_artifacts_cannot_be_a_native_run(self):
        # A missing-native-evidence guard, not a handwritten native journal.
        with self.assertRaises(AssertionError):
            validate_native({"inputs": [], "terminal": b"", "xlog": b"", "dumps": {}})


def validate_native(run):
    assert run["inputs"], "missing physical inputs"
    assert run["terminal"], "missing terminal"
    assert run["xlog"], "missing xlog"
    assert run["dumps"], "missing final dump"


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_TURNLOOP_EVIDENCE"), "native artifacts required"
)
class NativeOracleSensitivityTests(unittest.TestCase):
    def test_exact_current_mode_parity_and_repeats(self):
        root = Path(os.environ["NYARLATHACK_TURNLOOP_EVIDENCE"])
        baseline = read_native(root / "inactive")
        validate_native(baseline)
        for name in ("legacy-empty", "legacy-repeat", "v2-empty", "v2-repeat"):
            with self.subTest(mode=name):
                compare_runs(baseline, read_native(root / name))
        for a, b in (("legacy-empty", "legacy-repeat"), ("v2-empty", "v2-repeat")):
            self.assertEqual(
                (root / a / "run/events.jsonl").read_bytes(),
                (root / b / "run/events.jsonl").read_bytes(),
            )

    def test_each_changed_artifact_is_rejected(self):
        native = read_native(
            Path(os.environ["NYARLATHACK_TURNLOOP_EVIDENCE"]) / "v2-empty"
        )
        validate_native(native)
        for key in native:
            changed = dict(native)
            changed[key] = None
            with (
                self.subTest(field=key),
                self.assertRaisesRegex(AssertionError, key + " parity"),
            ):
                compare_runs(native, changed)

    def test_cross_build_dump_mismatch_is_not_suppressed(self):
        root = Path(os.environ["NYARLATHACK_TURNLOOP_EVIDENCE"])
        with self.assertRaisesRegex(AssertionError, "dumps parity"):
            compare_runs(
                read_native(root / "reviewed-chaos0"), read_native(root / "inactive")
            )


if __name__ == "__main__":
    unittest.main()
