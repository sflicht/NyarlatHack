"""Test-harness isolation regressions; no native games or compilers."""

import io
import os
import sys
import unittest

import test_episode_turnloop_provenance as provenance
import test_launcher as launcher


class TestIsolationTests(unittest.TestCase):
    def run_cases(self, *cases):
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.TestSuite(cases)
        )
        self.assertEqual(result.testsRun, len(cases), stream.getvalue())
        self.assertFalse(result.skipped, stream.getvalue())
        self.assertTrue(result.wasSuccessful(), stream.getvalue())

    def negative_case(self):
        return provenance.IntegrationTests(
            "test_missing_capture_fails_before_game_or_compiler"
        )

    def test_negative_driver_case_restores_original_umask(self):
        original = os.umask(0o022)
        self.addCleanup(os.umask, original)
        for mask in (0o022, 0o002, 0o027):
            with self.subTest(umask=oct(mask)):
                os.umask(mask)
                self.run_cases(self.negative_case())
                observed = os.umask(mask)
                self.assertEqual(observed, mask, "negative test leaked process umask")

    @unittest.skipUnless(
        sys.platform.startswith("linux"), "POSIX/Linux process fixtures"
    )
    def test_negative_driver_then_launcher_invalid_directories(self):
        original = os.umask(0o022)
        self.addCleanup(os.umask, original)
        # Run both cases in one process, without repairing state between them.
        # The launcher case uses Python stubs, not a native engine.
        self.run_cases(
            self.negative_case(),
            launcher.LauncherTests(
                "test_invalid_directories_and_executable_never_start_game"
            ),
        )


if __name__ == "__main__":
    unittest.main()
