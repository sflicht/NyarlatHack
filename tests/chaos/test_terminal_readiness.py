"""Offline Linux PTY regressions: quiet output is not an input boundary."""

import os
from pathlib import Path
import pty
import select
import signal
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gameplay_support import Game


# The gate is a pipe, not stdin: while held, the process cannot accept a key.
# No engine, event stream, preload library or model is needed by these tests.
SCRIPT = r"""
import os, sys, tty

tty.setraw(0)
gate, progress, split = map(int, sys.argv[1:])
def line():
    value = b''
    while not value.endswith(b'\n'):
        value += os.read(0, 1)
    return value
os.write(1, b'ready')
assert line() == b'#setsanity\n'
os.write(1, b'Set your sanity to what?')
assert line() == b'60\n'
os.write(1, b'Sanity changed.' + (b'\x1b[7m--Mo' if split else b''))
os.write(progress, b'G')
assert os.read(gate, 1) == b'G'
os.write(1, b're--\x1b[0m' if split else b'\x1b[7m--More--\x1b[0m')
while os.read(0, 1) != b' ':
    pass
os.write(1, b'ready')
assert os.read(0, 1) == b'.'
os.write(1, b'turn')
assert os.read(0, 1) == b'q'
os.write(1, b'bye')
"""


@unittest.skipUnless(sys.platform == "linux", "Linux terminal driver")
class TerminalReadinessTests(unittest.TestCase):
    def fixture(self, script=SCRIPT, split=False, supervised=False):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = root / "source"
        source.mkdir()
        (source / "dnethack").symlink_to(sys.executable)
        for name in ("nhdat", "license"):
            (source / name).touch()
        game = Game(source, "unused", observe=False, root=root / "session")
        gate_r, gate_w = os.pipe()
        progress_r, progress_w = os.pipe()
        for fd in (gate_r, progress_w):
            os.set_inheritable(fd, True)
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.close(gate_w)
                os.close(progress_r)
                if supervised:
                    worker = os.fork()
                    if worker:
                        os.close(gate_r)
                        os.close(progress_w)
                        _, status = os.waitpid(worker, 0)
                        os._exit(os.waitstatus_to_exitcode(status))
                os.execve(
                    str(game.game / "dnethack"),
                    [
                        "dnethack",
                        "-c",
                        script,
                        str(gate_r),
                        str(progress_w),
                        str(int(split)),
                    ],
                    dict(os.environ, PYTHONHOME=sys.base_prefix),
                )
            finally:
                os._exit(99)
        os.close(gate_r)
        os.close(progress_w)
        game.pid, game.fd = pid, fd

        def cleanup():
            # The fake supervisor and child share the pty.fork process group.
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            game.close()
            os.close(gate_w)
            os.close(progress_r)

        self.addCleanup(cleanup)
        return game, gate_w, progress_r

    def delayed_page(self, split, supervised):
        game, gate, progress = self.fixture(split=split, supervised=supervised)
        self.assertEqual(game.read(), b"ready")
        finished = threading.Event()
        results, errors = [], []

        def sanity():
            try:
                results.append(game.sanity(60))
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        thread = threading.Thread(target=sanity)
        thread.start()
        try:
            self.assertTrue(
                select.select([progress], [], [], 3)[0], "fixture not gated"
            )
            self.assertEqual(os.read(progress, 1), b"G")
            # Hold the output gap open beyond the old 100 ms heuristic.
            # The pipe handshake proves the writer is not waiting for input.
            premature = finished.wait(0.3)
        finally:
            os.write(gate, b"G")
            thread.join(4)
        self.assertFalse(thread.is_alive(), "driver did not finish after gate release")
        self.assertEqual(errors, [])
        self.assertFalse(premature, f"sanity returned before its page: {game.inputs}")
        self.assertEqual(results, [b"ready"])
        game.wait_turns(1)
        self.assertEqual(
            game.inputs, [b"#setsanity\n".hex(), b"60\n".hex(), "20", "2e"]
        )
        self.assertEqual(
            game.raw,
            b"readySet your sanity to what?Sanity changed.\x1b[7m--More--\x1b[0mreadyturn",
        )
        self.assertEqual(game.send("q"), b"bye")
        self.assertEqual(game.finish(b"bye"), 0)

    def test_delayed_more_is_consumed_before_next_command(self):
        self.delayed_page(split=False, supervised=False)

    def test_split_more_and_ansi_are_collected_at_one_input_boundary(self):
        self.delayed_page(split=True, supervised=False)

    def test_supervisor_wait_is_not_game_input_readiness(self):
        self.delayed_page(split=False, supervised=True)

    def test_supervised_split_more_is_consumed_before_next_command(self):
        self.delayed_page(split=True, supervised=True)

    def test_silent_input_boundary_does_not_require_output(self):
        game, _, _ = self.fixture(
            "import os, tty; tty.setraw(0); os.read(0, 1); os.read(0, 1)"
        )
        self.assertEqual(game.read(), b"")
        self.assertEqual(game.send("x"), b"")

    def test_stopped_stdin_reader_is_not_ready(self):
        game, _, _ = self.fixture(
            "import os, tty; tty.setraw(0); os.write(1, b'ready'); os.read(0, 1)"
        )
        self.assertEqual(game.read(), b"ready")
        os.kill(game.pid, signal.SIGSTOP)
        os.waitpid(game.pid, os.WUNTRACED)
        with self.assertRaisesRegex(AssertionError, "input readiness"):
            game.read(0.1)

    def test_previous_stdin_read_is_not_acknowledgement_of_new_input(self):
        game, _, _ = self.fixture(
            "import os, tty; tty.setraw(0); os.read(0, 1); os.read(0, 1)"
        )
        self.assertEqual(game.read(), b"")
        written, finished = threading.Event(), threading.Event()
        errors = []
        real_write = os.write

        def delayed_delivery(fd, value):
            # Model a write accepted before the PTY line discipline delivers it.
            self.assertEqual((fd, value), (game.fd, b"x"))
            written.set()
            return len(value)

        def send():
            try:
                game.send("x")
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()

        with patch("gameplay_support.os.write", side_effect=delayed_delivery):
            thread = threading.Thread(target=send)
            thread.start()
            try:
                self.assertTrue(written.wait(3))
                premature = finished.wait(0.1)
            finally:
                real_write(game.fd, b"x")
                thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertFalse(premature, "the previous blocked read acknowledged new input")

    def test_input_progress_cannot_validate_a_stale_stdin_snapshot(self):
        game, gate, progress = self.fixture(
            "import os, sys, tty; tty.setraw(0); os.write(1, b'ready'); "
            "assert os.read(0, 1) == b'x'; "
            "os.write(int(sys.argv[2]), b'G'); "
            "assert os.read(int(sys.argv[1]), 1) == b'G'; "
            "os.write(1, b'--More--'); os.read(0, 1)"
        )
        self.assertEqual(game.read(), b"ready")
        real_write, read_text = os.write, Path.read_text
        pending = False
        delivered = False
        proc = Path(f"/proc/{game.pid}")
        read_syscall = {"x86_64": "0", "aarch64": "63"}[os.uname().machine]
        gate_fd = int(read_text(proc / "cmdline").split("\0")[-4])

        def delayed_delivery(fd, value):
            nonlocal pending
            self.assertEqual((fd, value), (game.fd, b"x"))
            pending = True
            return len(value)

        def interleave(path, *args, **kwargs):
            nonlocal pending, delivered
            if not pending or path.parent != proc or path.name not in ("syscall", "io"):
                return read_text(path, *args, **kwargs)
            # Old ordering samples read(0) before delivery. Correct ordering
            # establishes progress first, then sees the child's real gate read.
            snapshot = (
                read_text(path, *args, **kwargs) if path.name == "syscall" else None
            )
            pending = False
            assert game.fd is not None
            real_write(game.fd, b"x")
            self.assertTrue(
                select.select([progress], [], [], 3)[0], "input not consumed"
            )
            self.assertEqual(os.read(progress, 1), b"G")
            deadline = time.monotonic() + 3
            while True:
                call = read_text(proc / "syscall").split()
                state = read_text(proc / "stat").rsplit(")", 1)[1].split()[0]
                if call[:2] == [read_syscall, hex(gate_fd)] and state == "S":
                    break
                self.assertLess(
                    time.monotonic(), deadline, "fixture not blocked on gate"
                )
                select.select([], [], [], 0.001)
            delivered = True
            return (
                snapshot if snapshot is not None else read_text(path, *args, **kwargs)
            )

        with (
            patch("gameplay_support.os.write", side_effect=delayed_delivery),
            patch.object(Path, "read_text", interleave),
            patch.object(game, "read", side_effect=lambda: Game.read(game, 0.2)),
        ):
            with self.assertRaisesRegex(AssertionError, "input readiness"):
                game.send("x")
        self.assertTrue(delivered, "controlled interleaving was not exercised")
        self.assertEqual(game.inputs, ["78"])
        self.assertEqual(game.raw, b"ready")
        real_write(gate, b"G")
        self.assertEqual(game.read(), b"--More--")

    def test_proc_permission_denial_fails_closed_with_diagnostic(self):
        game, _, _ = self.fixture(
            "import os, tty; tty.setraw(0); os.write(1, b'ready'); os.read(0, 1)"
        )
        self.assertEqual(game.read(), b"ready")
        read_text = Path.read_text

        def deny_syscall(path, *args, **kwargs):
            if path.name == "syscall":
                raise PermissionError("controlled proc denial")
            return read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", deny_syscall):
            with self.assertRaisesRegex(AssertionError, "readable Linux /proc"):
                game.read(0.1)

    def test_pipe_on_stdin_is_not_a_terminal_input_boundary(self):
        game, _, progress = self.fixture(
            "import os, sys; os.dup2(int(sys.argv[1]), 0); "
            "os.write(int(sys.argv[2]), b'G'); os.read(0, 1)"
        )
        self.assertTrue(select.select([progress], [], [], 3)[0])
        with self.assertRaisesRegex(AssertionError, "input readiness"):
            game.read(0.1)

    def test_other_pty_on_stdin_is_not_our_input_boundary(self):
        game, _, progress = self.fixture(
            "import os, pty, sys, tty; master, slave = pty.openpty(); "
            "tty.setraw(slave); os.dup2(slave, 0); os.close(slave); "
            "os.write(1, b'wrong terminal'); "
            "os.write(int(sys.argv[2]), b'G'); os.read(0, 1)"
        )
        self.assertTrue(select.select([progress], [], [], 3)[0])
        self.assertEqual(os.read(progress, 1), b"G")
        proc = Path(f"/proc/{game.pid}")
        self.assertFalse(
            os.path.samestat(os.stat(proc / "fd/0"), os.stat(proc / "fd/1"))
        )
        with self.assertRaisesRegex(AssertionError, "input readiness"):
            game.read(0.2)
        self.assertEqual(game.raw, b"wrong terminal")

    def test_quiet_nonterminal_read_times_out_and_preserves_output(self):
        game, _, progress = self.fixture(
            "import os, sys; os.write(1, b'partial'); "
            "os.write(int(sys.argv[2]), b'G'); os.read(int(sys.argv[1]), 1)"
        )
        self.assertTrue(select.select([progress], [], [], 3)[0])
        with self.assertRaisesRegex(AssertionError, "input readiness"):
            game.read(0.2)
        self.assertEqual(game.raw, b"partial")

    def test_continuous_output_cannot_extend_readiness_deadline(self):
        game, _, _ = self.fixture(
            "import os, time\nfor _ in range(30):\n os.write(1, b'x'); time.sleep(.02)"
        )
        with self.assertRaisesRegex(AssertionError, "input readiness"):
            game.read(0.2)
        self.assertTrue(game.raw)

    def test_exit_drains_output_without_requiring_an_input_prompt(self):
        game, _, _ = self.fixture("import os; os.write(1, b'final output')")
        self.assertEqual(game.read(), b"final output")
        self.assertEqual(game.finish(b"final output"), 0)


if __name__ == "__main__":
    unittest.main()
