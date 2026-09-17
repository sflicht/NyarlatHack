"""Linux-only, local children: no native helpers or game imports.

Each real test child has a five-second independent lifetime. pidfds acquired
while the child is handshake-blocked provide an outer, PID-reuse-safe guard.
"""

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "platform_supervision_under_test",
    Path(__file__).with_name("test_episode_platforms.py"),
)
platforms = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(platforms)

CHILD = """
import os, signal, sys, time
signal.alarm(5)
child = os.fork()
if child == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.alarm(5)
    print(os.getpid(), flush=True)
    while not os.path.exists(sys.argv[1]): time.sleep(.005)
    if sys.argv[2] == 'closed':
        os.close(1)
        os.close(2)
    while True: time.sleep(.05)
while not os.path.exists(sys.argv[1]): time.sleep(.005)
if sys.argv[2] in ('exit', 'closed'): os._exit(0)
while True: time.sleep(.05)
"""


@unittest.skipUnless(
    sys.platform == "linux" and hasattr(os, "pidfd_open"), "Linux ownership probes"
)
class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="platform-supervision-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assert_dead(self, pid):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                state = (
                    Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                )
            except FileNotFoundError:
                return
            if state == "Z":
                return  # Orphans are init's to reap; zombies cannot hold pipes.
            time.sleep(0.01)
        self.fail(f"descendant {pid} remained live")

    def guarded_command(self, mode):
        """Capture descendant pidfd before allowing leader/descendant to proceed."""
        original = subprocess.Popen
        held = []
        streams = []
        descendant = []

        def launch(*args, **kwargs):
            p = original(*args, **kwargs)
            held.append(os.pidfd_open(p.pid))
            streams.extend([p.stdout, p.stderr])
            import select

            self.assertTrue(select.select([p.stdout], [], [], 2)[0])
            pid = int(p.stdout.readline())
            descendant.append(pid)
            held.append(os.pidfd_open(pid))
            (self.root / "go").touch()
            return p

        try:
            with mock.patch.object(platforms.subprocess, "Popen", side_effect=launch):
                if mode == "closed":
                    platforms.bounded(
                        [sys.executable, "-c", CHILD, str(self.root / "go"), mode],
                        self.root,
                        dict(os.environ),
                        self.root / "probe",
                        timeout=2,
                    )
                else:
                    with self.assertRaises(TimeoutError):
                        platforms.bounded(
                            [sys.executable, "-c", CHILD, str(self.root / "go"), mode],
                            self.root,
                            dict(os.environ),
                            self.root / "probe",
                            timeout=0.15,
                        )
            self.assert_dead(descendant[0])
            self.assertTrue(all(s.closed for s in streams))
            self.assertTrue((self.root / "probe.stdout").exists())
            self.assertTrue((self.root / "probe.stderr").exists())
            status = json.loads((self.root / "probe.status.json").read_text())
            self.assertIn("cleanup", status)
        finally:
            for fd in held:
                try:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.close(fd)

    def test_exited_leader_does_not_abandon_pipe_holding_descendant(self):
        self.guarded_command("exit")

    def test_successful_leader_does_not_abandon_closed_pipe_descendant(self):
        self.guarded_command("closed")

    def test_term_responsive_leader_does_not_abandon_ignoring_descendant(self):
        self.guarded_command("wait")

    def test_reaped_identity_never_signals_a_group(self):
        with (
            mock.patch.object(platforms.os, "waitid", side_effect=ChildProcessError),
            mock.patch.object(platforms.os, "waitpid", side_effect=ChildProcessError),
            mock.patch.object(platforms.os, "killpg") as kill,
        ):
            try:
                platforms.terminate(123456789)
            except RuntimeError:
                pass
            self.assertEqual(kill.call_count, 0, "must prove ownership BEFORE killpg")

    def test_popen_acquisition_and_repeated_cleanup_signals(self):
        cancel = platforms.Cancellation()
        old = {
            s: signal.signal(s, cancel.handler)
            for s in (signal.SIGTERM, signal.SIGALRM)
        }
        original_popen, original_killpg = subprocess.Popen, os.killpg
        children = []
        signals = []

        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            # Popen returned internally, but bounded has not assigned it yet.
            os.kill(os.getpid(), signal.SIGTERM)
            return child

        def killpg(pid, sig):
            self.assertIsNone(children[0].returncode)
            # This must remain an unreaped child at BOTH group signals.
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            signals.append(sig)
            os.kill(os.getpid(), signal.SIGALRM)
            return original_killpg(pid, sig)

        try:
            with (
                mock.patch.object(platforms.subprocess, "Popen", side_effect=launch),
                mock.patch.object(platforms.os, "killpg", side_effect=killpg),
                self.assertRaises(TimeoutError),
            ):
                platforms.bounded(
                    [sys.executable, "-c", "import time; time.sleep(5)"],
                    self.root,
                    dict(os.environ),
                    self.root / "cancel",
                    cancel=cancel,
                )
            self.assertEqual(signals, [signal.SIGTERM, signal.SIGKILL])
            self.assertTrue(children[0].stdout.closed)
            self.assertTrue(children[0].stderr.closed)
            with self.assertRaises(ChildProcessError):
                os.waitpid(children[0].pid, os.WNOHANG)
            status = json.loads((self.root / "cancel.status.json").read_text())
            self.assertIn("TimeoutError", status["failure"])
            self.assertEqual(status["cleanup"]["errors"], [])
        finally:
            for sig, handler in old.items():
                signal.signal(sig, handler)
            for child in children:
                if child.returncode is None:
                    platforms.terminate(child.pid)
                    child.returncode = -signal.SIGKILL

    def test_cleanup_failure_retains_original_and_closes_descriptors(self):
        original_popen = subprocess.Popen
        children = []

        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            children.append(child)
            return child

        try:
            with (
                mock.patch.object(platforms.subprocess, "Popen", side_effect=launch),
                mock.patch.object(
                    platforms, "terminate", side_effect=RuntimeError("injected cleanup")
                ),
                self.assertRaises(TimeoutError) as caught,
            ):
                platforms.bounded(
                    [
                        sys.executable,
                        "-c",
                        "import sys,time; print('diagnostic', file=sys.stderr, flush=True); time.sleep(5)",
                    ],
                    self.root,
                    dict(os.environ),
                    self.root / "failure",
                    timeout=0.15,
                )
            self.assertIn("injected cleanup", str(caught.exception.__notes__))
            self.assertTrue(children[0].stdout.closed)
            self.assertTrue(children[0].stderr.closed)
            self.assertEqual(
                (self.root / "failure.stderr").read_bytes(), b"diagnostic\n"
            )
            status = json.loads((self.root / "failure.status.json").read_text())
            self.assertIn("injected cleanup", str(status["cleanup"]))
        finally:
            for child in children:
                child.returncode = platforms.terminate(child.pid)

    def test_game_acquisition_signal_records_child_before_checkpoint(self):
        self.assertTrue(
            hasattr(platforms, "owned_game_type"), "need private owned finish"
        )
        cancel = platforms.Cancellation()
        root = self.root

        class Base:
            def __init__(self):
                self.pid = self.fd = None
                self.root = root
                self.raw = bytearray()
                self.exitcode = None

            def start(self):
                import pty

                pid, fd = pty.fork()
                if pid == 0:
                    os.execl(
                        sys.executable,
                        sys.executable,
                        "-c",
                        "import time; time.sleep(5)",
                    )
                # Deterministic fork-return / ownership-assignment boundary.
                os.kill(os.getpid(), signal.SIGTERM)
                self.pid, self.fd = pid, fd
                return self.read()

            def read(self, initial=3):
                return b""

            def save_artifacts(self):
                (self.root / "saved").touch()

        game = platforms.owned_game_type(Base, cancel)()
        old = signal.signal(signal.SIGTERM, cancel.handler)
        try:
            with self.assertRaises(TimeoutError):
                game.start()
            self.assertIsNotNone(game.pid)
            pid, fd = game.pid, game.fd
            game.cleanup()
            self.assertIsNone(game.pid)
            self.assertIsNone(game.fd)
            with self.assertRaises(OSError):
                os.fstat(fd)
            with self.assertRaises(ChildProcessError):
                os.waitpid(pid, os.WNOHANG)
            self.assertTrue((self.root / "saved").exists())
        finally:
            game.cleanup()
            signal.signal(signal.SIGTERM, old)

    def test_game_exit_and_reap_signals_cannot_interrupt_cleanup(self):
        self.assertTrue(
            hasattr(platforms, "owned_game_type"), "need private owned finish"
        )
        cancel = platforms.Cancellation()
        root = self.root

        class Base:
            def save_artifacts(self):
                (root / "saved").touch()

        game = platforms.owned_game_type(Base, cancel)()
        child = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
        game.pid = child.pid
        game.fd = os.open(os.devnull, os.O_RDONLY)
        game.root = root
        game.exitcode = None
        original_waitid, original_waitpid = os.waitid, os.waitpid
        old = signal.signal(signal.SIGALRM, cancel.handler)
        try:
            deadline = time.monotonic() + 2
            while (
                original_waitid(
                    os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                )
                is None
            ):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)

            def observe(*args):
                result = original_waitid(*args)
                os.kill(os.getpid(), signal.SIGALRM)
                return result

            def reap(*args):
                result = original_waitpid(*args)
                os.kill(os.getpid(), signal.SIGALRM)
                return result

            with (
                mock.patch.object(platforms.os, "waitid", side_effect=observe),
                mock.patch.object(platforms.os, "waitpid", side_effect=reap),
            ):
                with self.assertRaises(TimeoutError):
                    game.finish(b"")
            self.assertIsNone(game.pid)
            self.assertIsNone(game.fd)
            self.assertEqual(game.exitcode, 0)
            self.assertTrue((root / "saved").exists())
        finally:
            game.cleanup()
            child.returncode = game.exitcode
            signal.signal(signal.SIGALRM, old)

    def test_catchable_signals_defer_until_checkpoint(self):
        self.assertTrue(
            hasattr(platforms, "Cancellation"), "need nonraising signal owner"
        )
        cancel = platforms.Cancellation()
        previous = {
            s: signal.signal(s, cancel.handler)
            for s in (signal.SIGTERM, signal.SIGALRM, signal.SIGINT)
        }
        try:
            for sig in previous:
                os.kill(os.getpid(), sig)
            self.assertEqual(cancel.signum, signal.SIGTERM)
            with self.assertRaises(TimeoutError):
                cancel.checkpoint()
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    unittest.main()
