"""Exit/reaping regressions, independent of native games and build artifacts."""

import errno
import json
import os
from pathlib import Path
import pty
import select
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import call, patch

from gameplay_support import Game


class FinishTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.pid, self.game.fd = 123, 456
        self.game.exitcode = None
        self.game.raw = bytearray()
        self.game.inputs = []
        self.game.sessions = []
        self.game._reader_pid = None
        self.game.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.now = 0.0
        self.enterContext(patch("gameplay_support.time.monotonic", lambda: self.now))
        self.sleep = self.enterContext(
            patch("gameplay_support.time.sleep", side_effect=self.advance)
        )
        self.close_fd = self.enterContext(patch("gameplay_support.os.close"))
        self.write = self.enterContext(patch("gameplay_support.os.write"))
        self.kill = self.enterContext(patch("gameplay_support.os.kill"))
        self.wait = self.enterContext(patch("gameplay_support.os.waitpid"))

    def advance(self, seconds):
        self.assertGreater(seconds, 0)
        self.now += seconds

    def delayed_exit(self, status=0):
        self.wait.side_effect = lambda pid, flags: (
            (pid, status) if self.now >= 0.1 else (0, 0)
        )

    def test_eof_before_waitable_yields_then_reaps(self):
        self.delayed_exit()
        with patch.object(self.game, "read", return_value=b""):
            self.assertEqual(self.game.finish(b""), 0)
        self.assertGreaterEqual(self.now, 0.1)
        self.assertTrue(self.sleep.called)
        self.write.assert_not_called()
        self.assertIsNone(self.game.pid)
        self.assertIsNone(self.game.fd)
        self.close_fd.assert_called_once_with(456)
        self.assertEqual(
            json.loads((self.game.root / "manifest.json").read_text())["exit"], 0
        )

    def test_never_waitable_eof_reaches_deadline_and_remains_owned(self):
        self.wait.return_value = (0, 0)
        with patch.object(self.game, "read", return_value=b""):
            with self.assertRaisesRegex(AssertionError, "game failed to exit"):
                self.game.finish(b"")
        self.assertAlmostEqual(self.now, 8.0)
        self.assertEqual((self.game.pid, self.game.fd), (123, 456))
        self.assertIsNone(self.game.exitcode)
        self.close_fd.assert_not_called()
        self.write.assert_not_called()
        self.wait.return_value = (123, signal.SIGTERM)
        self.game.close()
        self.kill.assert_called_once_with(123, signal.SIGTERM)
        self.wait.assert_called_with(123, 0)
        self.close_fd.assert_called_once_with(456)
        self.assertIsNone(self.game.pid)
        self.assertIsNone(self.game.fd)

    def test_delayed_exit_preserves_exact_prompt_inputs(self):
        self.delayed_exit()
        with patch.object(
            self.game,
            "read",
            side_effect=[b"disclose? [ynq]", b"--More--", b""] + [b""] * 100,
        ):
            self.assertEqual(self.game.finish(b"--More--"), 0)
        self.assertEqual(self.game.inputs, ["20", "6e", "20"])
        self.assertEqual(
            self.write.call_args_list,
            [call(456, b" "), call(456, b"n"), call(456, b" ")],
        )

    def test_nonzero_exit_status_is_preserved(self):
        self.delayed_exit(7 << 8)
        with patch.object(self.game, "read", return_value=b""):
            self.assertEqual(self.game.finish(b""), 7)
        self.assertEqual(
            json.loads((self.game.root / "manifest.json").read_text())["exit"], 7
        )

    def test_signal_exit_status_is_preserved(self):
        self.wait.return_value = (123, signal.SIGTERM)
        self.assertEqual(self.game.finish(b""), -signal.SIGTERM)

    def test_prompt_count_remains_bounded(self):
        self.wait.return_value = (0, 0)
        with patch.object(self.game, "read", return_value=b"[ynq]"):
            with self.assertRaisesRegex(AssertionError, "game failed to exit"):
                self.game.finish(b"[ynq]")
        self.assertEqual(self.game.inputs, ["6e"] * 40)

    def test_nested_prompt_reads_share_remaining_deadline(self):
        self.wait.return_value = (0, 0)
        budgets = []

        def read(initial=3.0):
            budgets.append(initial)
            self.advance(initial)
            return b"[ynq]"

        with patch.object(self.game, "read", side_effect=read):
            with self.assertRaisesRegex(AssertionError, "game failed to exit"):
                self.game.finish(b"[ynq]")
        self.assertEqual(budgets, [3.0, 3.0, 2.0])
        self.assertEqual(self.now, 8.0)
        self.assertEqual(self.game.inputs, ["6e"] * 3)

    def test_passive_reads_share_remaining_deadline(self):
        self.wait.return_value = (0, 0)
        budgets = []

        def read(initial=3.0):
            self.assertLessEqual(initial, 8.0 - self.now)
            budgets.append(initial)
            self.advance(initial)
            return b"shutdown output"

        with patch.object(self.game, "read", side_effect=read):
            with self.assertRaisesRegex(AssertionError, "game failed to exit"):
                self.game.finish(b"")
        self.assertAlmostEqual(self.now, 8.0)
        self.assertLess(budgets[-1], 0.2)
        self.write.assert_not_called()

    def test_read_error_is_not_swallowed_and_cleanup_still_owns_handles(self):
        self.wait.return_value = (0, 0)
        with patch.object(
            self.game, "read", side_effect=OSError(errno.EBADF, "bad fd")
        ):
            with self.assertRaises(OSError):
                self.game.finish(b"")
        self.assertEqual((self.game.pid, self.game.fd), (123, 456))
        self.game.close()
        self.kill.assert_called_once_with(123, signal.SIGTERM)
        self.close_fd.assert_called_once_with(456)

    def test_wait_error_is_not_swallowed(self):
        self.wait.side_effect = ChildProcessError("not our child")
        with self.assertRaises(ChildProcessError):
            self.game.finish(b"")
        self.assertEqual((self.game.pid, self.game.fd), (123, 456))

    def test_artifact_error_propagates_after_handles_are_released(self):
        self.wait.return_value = (123, 0)
        with patch.object(
            self.game, "save_artifacts", side_effect=OSError("disk full")
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.game.finish(b"")
        self.assertIsNone(self.game.pid)
        self.assertIsNone(self.game.fd)
        self.assertEqual(self.game.exitcode, 0)


@unittest.skipUnless(sys.platform == "linux", "Linux PTY EOF/EIO")
class RealPtyFinishTests(unittest.TestCase):
    def test_slave_closes_before_child_exits(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        game = Game.__new__(Game)
        game.root, game.raw, game.inputs, game.sessions = root, bytearray(), [], []
        game.exitcode = None
        game._reader_pid = None
        ready_r, ready_w = os.pipe()
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.close(ready_r)
                signal.signal(signal.SIGHUP, signal.SIG_IGN)
                for slave in (0, 1, 2):
                    os.close(slave)
                os.write(ready_w, b"closed")
                time.sleep(0.2)
                os._exit(7)
            finally:
                os._exit(99)
        os.close(ready_w)
        game.pid, game.fd = pid, fd

        def cleanup():
            # Only our child: force termination before close's blocking reap.
            if game.pid is not None:
                try:
                    os.kill(game.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            game.close()
            os.close(ready_r)

        self.addCleanup(cleanup)
        self.assertTrue(select.select([ready_r], [], [], 3)[0])
        self.assertEqual(os.read(ready_r, 6), b"closed")
        started = time.monotonic()
        self.assertEqual(game.read(0.1), b"")
        self.assertEqual(game.finish(b""), 7)
        self.assertLess(time.monotonic() - started, 9)
        self.assertEqual(game.inputs, [])
        self.assertIsNone(game.pid)
        self.assertIsNone(game.fd)
        with self.assertRaises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)


if __name__ == "__main__":
    unittest.main()
