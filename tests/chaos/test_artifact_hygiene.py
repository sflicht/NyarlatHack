"""Temp dirs are removed after success and kept on failure or on request."""

import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import artifact_hygiene as hygiene

ROOT = Path(__file__).resolve().parents[2]
CLEAN = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS",)}
CLEAN.pop(hygiene.KEEP_ENV, None)


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("/", "_") + "_hygiene_unit", ROOT / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Base(unittest.TestCase):
    def setUp(self):
        base = tempfile.TemporaryDirectory(prefix="hygiene-unit-")
        self.addCleanup(base.cleanup)
        self.base = Path(base.name)
        patcher = mock.patch.dict(os.environ, CLEAN, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_case(self, case):
        result = unittest.TestResult()
        with mock.patch("sys.stderr", io.StringIO()):
            unittest.defaultTestLoader.loadTestsFromTestCase(case).run(result)
        return result


class RetainOnFailureTests(Base):
    def cases(self):
        base = self.base

        class Case(hygiene.RetainOnFailure):
            made = {}

            def mk(self, name):
                path = Path(tempfile.mkdtemp(prefix=name + "-", dir=base))
                (path / "events.jsonl").write_text("{}")
                Case.made[name] = path
                return hygiene.track(self, path)

            def test_pass(self):
                self.mk("pass")

            def test_fail(self):
                self.mk("fail")
                self.fail("deliberate")

            def test_error(self):
                self.mk("error")
                raise RuntimeError("deliberate")

        return Case

    def test_passing_test_dirs_removed_failures_kept(self):
        case = self.cases()
        result = self.run_case(case)
        self.assertEqual((len(result.failures), len(result.errors)), (1, 1))
        self.assertFalse(case.made["pass"].exists())
        self.assertTrue(case.made["fail"].exists())
        self.assertTrue(case.made["error"].exists())

    def test_keep_env_retains_everything(self):
        os.environ[hygiene.KEEP_ENV] = "1"
        case = self.cases()
        self.run_case(case)
        self.assertTrue(case.made["pass"].exists())

    def test_github_actions_retains_for_upload(self):
        os.environ["GITHUB_ACTIONS"] = "true"
        case = self.cases()
        self.run_case(case)
        self.assertTrue(case.made["pass"].exists())

    def test_class_artifacts_follow_class_outcome(self):
        base = self.base

        def make_case(fail):
            class Case(hygiene.RetainOnFailure):
                @classmethod
                def setUpClass(cls):
                    cls.root = Path(
                        cls.track_class_artifacts(tempfile.mkdtemp(dir=base))
                    )

                def test_a(self):
                    pass

                def test_b(self):
                    if fail:
                        self.fail("deliberate")

            return Case

        good, bad = make_case(False), make_case(True)
        self.run_case(good)
        self.run_case(bad)
        self.assertFalse(good.root.exists())
        self.assertTrue(bad.root.exists())

    def test_plain_testcase_helpers_still_work_and_retain(self):
        path = Path(tempfile.mkdtemp(dir=self.base))
        self.assertEqual(hygiene.track(unittest.TestCase(), path), path)
        self.assertEqual(hygiene.track_running(path), path)
        self.assertTrue(path.exists())

    def test_remove_tree_never_follows_symlinks(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "keep").write_text("keep")
        victim = self.base / "victim"
        victim.mkdir()
        (victim / "link").symlink_to(outside, target_is_directory=True)
        locked = victim / "locked"
        locked.mkdir()
        (locked / "f").write_text("x")
        locked.chmod(0o500)
        self.assertTrue(hygiene.remove_tree(victim))
        self.assertEqual((outside / "keep").read_text(), "keep")
        top = self.base / "top-link"
        top.symlink_to(outside, target_is_directory=True)
        self.assertTrue(hygiene.remove_tree(top))
        self.assertTrue((outside / "keep").exists())


class SeedSweepTidyTests(Base):
    def setUp(self):
        super().setUp()
        self.sweep = load_script("scripts/seed_sweep.py")

    def work(self):
        path = Path(tempfile.mkdtemp(prefix="nyarl-sweep-", dir=self.base))
        (path / "bard-00001").mkdir()
        return path

    def test_success_removes_owned_work(self):
        work = self.work()
        games = [{"outcome": "died"}, {"outcome": "turn_limit"}]
        self.assertTrue(self.sweep.tidy_work(work, True, games, environ={}))
        self.assertFalse(work.exists())

    def test_failure_or_request_or_explicit_work_keeps(self):
        for owned, games, env in (
            (True, None, {}),
            (True, [{"outcome": "harness_error"}], {}),
            (True, [{"outcome": "died"}], {hygiene.KEEP_ENV: "1"}),
            (False, [{"outcome": "died"}], {}),
        ):
            with self.subTest(owned=owned, games=games, env=env):
                work = self.work()
                with mock.patch("sys.stdout", io.StringIO()):
                    self.assertFalse(
                        self.sweep.tidy_work(work, owned, games, environ=env)
                    )
                self.assertTrue(work.exists())


class NativeRunnerTidyTests(Base):
    def setUp(self):
        super().setUp()
        self.runner = load_script("scripts/run_native_tests.py")
        self.fixtures = self.base / "fixtures"
        self.fixtures.mkdir()
        self.old = self.fixtures / "earlier-run"
        self.old.mkdir()
        self.before = set(self.fixtures.iterdir())
        self.invocation = self.fixtures / "full-suite.abc"
        self.invocation.mkdir()
        (self.invocation / "full-suite.log").write_text("OK\n")
        self.made = self.fixtures / "nyarl-curio-state-xyz"
        self.made.mkdir()

    def tidy(self, code, env):
        with mock.patch("sys.stdout", io.StringIO()):
            return self.runner.tidy_fixtures(
                self.fixtures, self.before, self.invocation, code, environ=env
            )

    def test_success_removes_only_new_fixture_dirs_keeps_log(self):
        self.assertEqual(self.tidy(0, {}), [self.made])
        self.assertFalse(self.made.exists())
        self.assertTrue((self.invocation / "full-suite.log").exists())
        self.assertTrue(self.old.exists())

    def test_failure_or_keep_retains(self):
        for code, env in ((1, {}), (0, {hygiene.KEEP_ENV: "1"})):
            with self.subTest(code=code, env=env):
                self.assertEqual(self.tidy(code, env), [])
                self.assertTrue(self.made.exists())

    def test_keep_request_reaches_suite_environment(self):
        os.environ[hygiene.KEEP_ENV] = "1"
        data = {
            "build_output": str(self.base),
            "receipt": "r",
            "revision": "0" * 40,
            "profile": "core",
        }
        env = self.runner.suite_environment(self.base / "d.json", data)
        self.assertEqual(env[hygiene.KEEP_ENV], "1")
        del os.environ[hygiene.KEEP_ENV]
        env = self.runner.suite_environment(self.base / "d.json", data)
        self.assertNotIn(hygiene.KEEP_ENV, env)


if __name__ == "__main__":
    unittest.main()
