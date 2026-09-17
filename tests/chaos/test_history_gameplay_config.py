"""Configuration-only probes: no native execution or build acceptance."""

import os
from pathlib import Path
import unittest
from unittest import mock

import test_history_gameplay as subject


class HistoryNativeConfigurationTests(unittest.TestCase):
    def invoke(self):
        subject.HistoryGameplayNativeTests(
            "test_explicit_native_driver"
        ).test_explicit_native_driver()

    def invoke_configured(self):
        try:
            self.invoke()
        except unittest.SkipTest as exc:
            raise RuntimeError(
                "a configured native profile must not be skipped"
            ) from exc

    def test_wholly_unconfigured_skips(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(unittest.SkipTest):
                self.invoke()

    def test_existing_common_native_profile_drives_fixture(self):
        env = {
            "NYARLATHACK_GAME_TESTS": "1",
            "NYARLATHACK_NATIVE_FIXTURE_MODE": "source-build",
            "NYARLATHACK_NATIVE_BUILD_RECEIPT": "/private/receipt",
            "NYARLATHACK_NATIVE_EXPECTED_REVISION": "a" * 40,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "native_driver_supervision.run_driver",
                return_value=(0, Path("synthetic-driver-log")),
            ) as run:
                self.invoke_configured()
        self.assertEqual(run.call_count, 1)
        script, arguments, root, artifacts = run.call_args.args
        self.assertEqual(script, Path(subject.__file__).resolve())
        self.assertEqual(root, Path(subject.__file__).resolve().parents[2])
        values = dict(zip(arguments[::2], arguments[1::2]))
        self.assertEqual(values["--root"], str(root))
        self.assertEqual(values["--receipt"], "/private/receipt/1-manifest.json")
        self.assertEqual(values["--revision"], "a" * 40)
        self.assertEqual(values["--output"], str(artifacts))
        self.assertFalse(artifacts.exists())
        self.assertEqual(artifacts.parent.stat().st_mode & 0o777, 0o700)
        self.addCleanup(artifacts.parent.rmdir)

    def test_partial_common_profile_fails_closed(self):
        for name in ("NYARLATHACK_GAME_TESTS", "NYARLATHACK_NATIVE_BUILD_RECEIPT"):
            with self.subTest(name=name):
                with mock.patch.dict(os.environ, {name: "1"}, clear=True):
                    with self.assertRaises(AssertionError):
                        self.invoke_configured()

    def test_wrong_mode_fails_before_launch(self):
        env = {
            "NYARLATHACK_GAME_TESTS": "1",
            "NYARLATHACK_NATIVE_FIXTURE_MODE": "archived",
            "NYARLATHACK_NATIVE_BUILD_RECEIPT": "/private/receipt",
            "NYARLATHACK_NATIVE_EXPECTED_REVISION": "a" * 40,
        }
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("native_driver_supervision.run_driver") as run:
                with self.assertRaises(AssertionError):
                    self.invoke_configured()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
