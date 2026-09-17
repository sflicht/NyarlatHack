"""Synthetic descriptor/runner checks; no game, build or native acceptance."""

import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
REVISION = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
).strip()


class DescriptorTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("native_fixture_config"),
            "shared descriptor missing",
        )
        return importlib.import_module("native_fixture_config")

    def fixture(self, base):
        for name in ("receipts", "artifacts", "build"):
            (base / name).mkdir(mode=0o700)
        data = dict(
            schema=1,
            root=str(ROOT),
            revision=REVISION,
            receipt=str(base / "receipts"),
            artifact_parent=str(base / "artifacts"),
            build_output=str(base / "build"),
            profile="core",
            historical_stock=None,
        )
        path = base / "descriptor.json"
        path.write_text(json.dumps(data))
        path.chmod(0o600)
        return path, data

    def test_unconfigured_is_not_native_acceptance(self):
        api = self.api()
        self.assertIsNone(api.family("whistle", ROOT, {}))

    def test_oracle_context_does_not_enable_live_execution(self):
        api = self.api()
        cases = (
            ("turnloop", {"NYARLATHACK_TURNLOOP_EVIDENCE": "/synthetic/evidence"}),
            ("fountain", {"NYARLATHACK_FOUNTAIN_EVIDENCE": "/synthetic/evidence"}),
            ("delivery", {"NYARLATHACK_NATIVE_FIXTURE_MODE": "archived"}),
        )
        for name, context in cases:
            with self.subTest(name=name):
                self.assertFalse(api.enabled(name, context))
                flag = (
                    "NYARLATHACK_TURNLOOP_TESTS"
                    if name == "turnloop"
                    else "NYARLATHACK_GAME_TESTS"
                )
                self.assertFalse(api.enabled(name, dict(context, **{flag: "0"})))
                self.assertTrue(api.enabled(name, dict(context, **{flag: "1"})))
                # Even a malformed explicit descriptor must reach validation,
                # rather than turn into a misleading disabled-test skip.
                self.assertTrue(
                    api.enabled(name, {"NYARLATHACK_NATIVE_DESCRIPTOR": ""})
                )

    def test_valid_family_mapping_absent_leaf_and_no_new_prefix(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            path, data = self.fixture(Path(tmp))
            env = {
                "NYARLATHACK_NATIVE_DESCRIPTOR": str(path),
                "NYARLATHACK_NATIVE_EXPECTED_REVISION": REVISION,
            }
            for name in api.FAMILIES:
                if name == "turnloop":
                    self.assertIsNone(api.family(name, ROOT, env))
                    continue
                value = api.family(name, ROOT, env)
                self.assertEqual(value["root"], str(ROOT))
                self.assertEqual(
                    value["artifacts"], str(Path(data["artifact_parent"]) / name)
                )
            with mock.patch.dict(api.FAMILIES, {"synthetic": "SYNTHETIC"}):
                self.assertEqual(
                    api.family("synthetic", ROOT, env)["revision"], REVISION
                )
            (Path(data["artifact_parent"]) / "whistle").mkdir()
            with self.assertRaises(ValueError):
                api.family("whistle", ROOT, env)

    def test_strict_schema_revision_root_and_paths(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            path, data = self.fixture(Path(tmp))
            for key, value in (
                ("schema", 2),
                ("schema", True),
                ("extra", 0),
                ("root", str(Path(tmp))),
                ("revision", "a" * 40),
                ("receipt", str(Path(tmp)) + "/../receipts"),
                ("profile", "unknown"),
                ("historical_stock", {}),
            ):
                with self.subTest(key=key, value=value):
                    path.write_text(json.dumps(dict(data, **{key: value})))
                    with self.assertRaises(ValueError):
                        api.load(path, ROOT, REVISION)
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                api.load(path, ROOT, "HEAD")
            del data["receipt"]
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                api.load(path, ROOT, REVISION)

    def test_private_owned_bounded_strict_json_not_links(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            path, data = self.fixture(Path(tmp))
            for raw in ('{"schema":1,"schema":1}', "NaN", "x" * 17000):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    api.load(path, ROOT, REVISION)
            path.write_text(json.dumps(data))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                api.load(path, ROOT, REVISION)
            path.chmod(0o600)
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                api.load(link, ROOT, REVISION)
            link.unlink()
            os.link(path, link)
            with self.assertRaises(ValueError):
                api.load(path, ROOT, REVISION)
            link.unlink()
            Path(data["artifact_parent"]).chmod(0o755)
            with self.assertRaises(ValueError):
                api.load(path, ROOT, REVISION)

    def test_partial_and_mixed_configuration_rejected(self):
        api = self.api()
        for env in (
            {"NYARLATHACK_WHISTLE_ROOT": str(ROOT)},
            {"NYARLATHACK_NATIVE_DESCRIPTOR": ""},
            {
                "NYARLATHACK_NATIVE_DESCRIPTOR": "/missing",
                "NYARLATHACK_WHISTLE_ROOT": str(ROOT),
            },
        ):
            with self.subTest(env=env), self.assertRaises(ValueError):
                api.family("whistle", ROOT, env)


class RunnerTests(unittest.TestCase):
    def api(self):
        path = ROOT / "scripts/run_native_tests.py"
        self.assertTrue(path.exists(), "official entry point missing")
        spec = importlib.util.spec_from_file_location("native_runner_unit", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_optimized_runner_rejects_before_preparation(self):
        # A sentinel replaces preparation, not its assertion-heavy validation.
        # The real CLI must reject optimization before it can reach this call.
        probe = (
            "import runpy, sys; from pathlib import Path; "
            "sys.path.insert(0, str(Path(sys.argv[1]) / 'tests/chaos')); "
            "import native_fixture_selection as selection; "
            "selection.prepare = lambda *a: sys.exit('PREPARATION REACHED'); "
            "sys.argv = [str(Path(sys.argv[1]) / 'scripts/run_native_tests.py'), "
            "'--root', sys.argv[1], '--expected-revision', sys.argv[2], "
            "'--build-output', sys.argv[3]]; "
            "runpy.run_path(sys.argv[0], run_name='__main__')"
        )
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("fixtures", "home", "system-gcc13"):
                (base / name).mkdir(mode=0o700)
            for flag in ("-O", "-OO"):
                with self.subTest(flag=flag):
                    result = subprocess.run(
                        [
                            "/usr/bin/python3",
                            "-B",
                            flag,
                            "-c",
                            probe,
                            str(ROOT),
                            REVISION,
                            tmp,
                        ],
                        env={"PATH": "/usr/bin:/bin"},
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("optimized Python is not supported", result.stderr)
                    self.assertNotIn("PREPARATION REACHED", result.stderr)
                    self.assertEqual(list((base / "fixtures").iterdir()), [])

    def test_real_unittest_exit_not_printed_status(self):
        runner = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for fail in (False, True):
                (base / "test_noise.py").write_text(
                    "import unittest, sys\nclass Noise(unittest.TestCase):\n"
                    " def test_noise(self):\n"
                    "  sys.stdout.write('FAIL'); sys.stdout.flush()\n"
                    "  sys.stdout.write('ED (fake)\\nOK\\n\\nOK (skipped=9)\\n')\n"
                    f"  self.assertFalse({fail!r})\n"
                )
                code = runner.run_unittest(
                    base,
                    {"PATH": "/usr/bin:/bin"},
                    base / f"{fail}.log",
                    start=".",
                    pattern="test_noise.py",
                )
                self.assertEqual(code, int(fail))
                output = (base / f"{fail}.log").read_text()
                self.assertIn("FAIL", output)
                self.assertIn("ED (fake)", output)
                self.assertIn("OK (skipped=9)", output)

    def test_child_creation_mask_and_private_log(self):
        runner = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "test_permissions.py").write_text(
                "import unittest, pathlib, stat\n"
                "class Permissions(unittest.TestCase):\n"
                " def test_creation(self):\n"
                "  p=pathlib.Path('created'); p.touch()\n"
                "  self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o644)\n"
            )
            old_mask = os.umask(0o077)
            try:
                code = runner.run_unittest(
                    base,
                    {"PATH": "/usr/bin:/bin"},
                    base / "suite.log",
                    start=".",
                    pattern="test_permissions.py",
                )
            finally:
                os.umask(old_mask)
            self.assertEqual(code, 0)
            self.assertEqual((base / "suite.log").stat().st_mode & 0o777, 0o600)
            self.assertEqual((base / "created").stat().st_mode & 0o777, 0o644)

    def test_sanitized_environment_legacy_bridge_only(self):
        runner = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            path, data = DescriptorTests().fixture(Path(tmp))
            with mock.patch.dict(
                os.environ,
                {
                    "PYTHONPATH": "/hostile",
                    "OPENAI_API_KEY": "fake",
                    "NYARLATHACK_OBSERVATIONS": "1",
                },
            ):
                env = runner.suite_environment(path, data)
            for key in (
                "PYTHONPATH",
                "OPENAI_API_KEY",
                "NYARLATHACK_OBSERVATIONS",
                "NYARLATHACK_WHISTLE_ROOT",
            ):
                self.assertNotIn(key, env)
            self.assertEqual(env["NYARLATHACK_NATIVE_DESCRIPTOR"], str(path))
            self.assertEqual(env["NYARLATHACK_NATIVE_EXPECTED_REVISION"], REVISION)
            self.assertEqual(env["NYARLATHACK_NATIVE_FIXTURE_MODE"], "source-build")

    def test_ci_and_docs_share_official_entry_point(self):
        for name in (".github/workflows/quality.yml", "docs/quality-control.md"):
            text = (ROOT / name).read_text()
            self.assertIn("scripts/run_native_tests.py", text)
            self.assertIn('--build-output "$out"', text)
            self.assertNotIn("NYARLATHACK_WHISTLE_ROOT=", text)
            self.assertNotIn("NYARLATHACK_FOUNTAIN_ROOT=", text)
        workflow = (ROOT / ".github/workflows/quality.yml").read_text()
        self.assertIn("ruff==0.15.10", workflow)
        self.assertNotIn("-m unittest discover", workflow)
