"""Offline launcher integration tests use real Python subprocesses, not a game build."""

from contextlib import redirect_stderr
import fcntl
import io
import json
import os
from pathlib import Path
import pty
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]

GAME = """#!/usr/bin/env python3
import fcntl, json, os, pathlib, signal, sys, time
run = pathlib.Path(os.environ['NYARLATHACK_RUN_DIR'])
lock = os.open(run / '.director.lock', os.O_RDWR)
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    locked = False
except BlockingIOError:
    locked = True
os.close(lock)
siblings = pathlib.Path('/proc/%s/task/%s/children' % (os.getppid(), os.getppid())).read_text().split()
info = dict(args=sys.argv[1:], cwd=os.getcwd(), run=str(run), locked=locked,
            tty=os.isatty(0), pid=os.getpid(), director=[int(x) for x in siblings if int(x) != os.getpid()],
            mailbox=(run / 'whisper.json').exists(),
            nethackoptions=os.environ.get('NETHACKOPTIONS'))
pathlib.Path(os.environ['GAME_MARKER']).write_text(json.dumps(info))
mode = os.environ.get('GAME_MODE', '')
if mode == 'ignore_term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    pathlib.Path(os.environ['GAME_MARKER'] + '.ignoring').touch()
    while True: time.sleep(.02)
if mode == 'wait':
    while True: time.sleep(.02)
if mode == 'director_dies':
    os.kill(info['director'][0], signal.SIGKILL)
    time.sleep(.2)
    lock = os.open(run / '.director.lock', os.O_RDWR)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sys.exit(91)
    except BlockingIOError:
        pass
    os.close(lock)
    pathlib.Path(os.environ['GAME_MARKER'] + '.survived').touch()
if mode in ('random_event', 'death_event', 'partial_event'):
    event = dict(v=3, cosmetic=dict(seen=0, last_turn=0), seq=1, turn=1, safe=1, event='safe_point', phase='result',
                 detail='pray', sanity=80, insight=0, budget=4, spent=0, reserved=0, last_id=0)
    if mode == 'death_event': event['event'] = 'death'
    target = run / 'events.jsonl'
    target.touch(mode=0o600)
    if mode == 'partial_event':
        raw = json.dumps(event) + '\\n'
        target.write_text(raw[:12])
        time.sleep(.15)
        with target.open('a') as f: f.write(raw[12:])
    else:
        target.write_text(json.dumps(event) + '\\n')
    target.chmod(0o600)
    if mode == 'death_event':
        time.sleep(.2)
    else:
        deadline = time.monotonic() + 3
        while not (run / 'whisper.json').exists() and time.monotonic() < deadline: time.sleep(.01)
        if not (run / 'whisper.json').exists(): sys.exit(92)
if mode == 'signal':
    os.kill(os.getpid(), int(os.environ.get('GAME_SIGNAL', str(signal.SIGTERM))))
print(json.dumps(info), flush=True)
sys.exit(int(os.environ.get('GAME_STATUS', '0')))
"""


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX/Linux process fixtures")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.root = self.path / "game root"
        self.root.mkdir()
        self.game = self.root / "dnethack"
        self.game.write_text(GAME)
        self.game.chmod(0o700)
        self.marker = self.path / "started.json"
        self.env = dict(os.environ, GAME_MARKER=str(self.marker), TMPDIR=str(self.path))
        self.command = [
            sys.executable,
            "-m",
            "chaos",
            "play",
            "--game-root",
            str(self.root),
        ]

    def run_cli(self, *args, **env):
        return subprocess.run(
            self.command + list(args),
            cwd=ROOT,
            env=dict(self.env, **env),
            text=True,
            capture_output=True,
            timeout=10,
        )

    def info(self):
        return json.loads(self.marker.read_text())

    def assert_reaped(self, info):
        self.assertEqual(len(info["director"]), 1)
        for pid in info["director"]:
            self.assertFalse(
                Path("/proc", str(pid)).exists(), "director must be reaped"
            )
        with open(Path(info["run"]) / ".director.lock", "rb") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def start_waiting(self, *args, **env):
        p = subprocess.Popen(
            self.command + list(args),
            cwd=ROOT,
            env=dict(self.env, GAME_MODE="wait", **env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def cleanup():
            if p.poll() is None:
                p.terminate()
            try:
                p.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
                p.communicate()

        self.addCleanup(cleanup)
        deadline = time.monotonic() + 5
        while (
            not self.marker.exists()
            and p.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        if not self.marker.exists():
            p.terminate()
            out, err = p.communicate(timeout=5)
            self.fail("game did not start: " + out + err)
        return p

    def test_default_pack_fresh_private_directory_args_and_exit(self):
        args = ["-D", "-u", "name with spaces", "$(touch NEVER)", "--odd=value"]
        p = self.run_cli("--", *args, GAME_STATUS="7")
        self.assertEqual(p.returncode, 7, p.stderr)
        info = self.info()
        self.assertEqual(info["args"], args)
        self.assertEqual(info["cwd"], str(self.root))
        self.assertTrue(info["mailbox"])
        self.assertTrue(info["locked"])
        run = Path(info["run"])
        self.assertEqual(run.stat().st_mode & 0o777, 0o700)
        self.assertIn(json.dumps(str(run)), p.stderr)
        self.assertEqual(
            json.loads((run / "whisper.json").read_text())["mutation"], "ambient"
        )
        self.assert_reaped(info)
        self.assertEqual(self.run_cli().returncode, 0)
        self.assertNotEqual(self.info()["run"], str(run))

    def test_all_packs_and_explicit_fresh_path(self):
        for pack, mutation in [
            ("ambient", "ambient"),
            ("silence", "ambient"),
            ("ward", "ward_efficacy"),
            ("hunger", "hunger_rate"),
        ]:
            with self.subTest(pack=pack):
                run = self.path / pack
                p = self.run_cli(
                    "--pack", pack, "--run-dir", str(run), "--at", "2", "--id", "3"
                )
                self.assertEqual(p.returncode, 0, p.stderr)
                request = json.loads((run / "whisper.json").read_text())
                self.assertEqual(
                    (request["mutation"], request["at"], request["id"]),
                    (mutation, 2, 3),
                )

    def test_random_offline_seed_and_reuse_preserve_data(self):
        run = self.path / "restore"
        run.mkdir(mode=0o700)
        (run / "keep").write_text("saved data")
        p = self.run_cli(
            "--backend",
            "random",
            "--seed",
            "7",
            "--ordinary-food",
            "--reuse-run-dir",
            str(run),
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(self.info()["mailbox"])
        self.assertEqual((run / "keep").read_text(), "saved data")
        self.assert_reaped(self.info())

    def test_random_seed_produces_repeatable_real_subprocess_proposals(self):
        requests = []
        for seed in (None, "0", "7", "7"):
            options = [] if seed is None else ["--seed", seed]
            p = self.run_cli(
                "--backend",
                "random",
                "--poll",
                ".01",
                *options,
                GAME_MODE="random_event",
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            requests.append(
                json.loads((Path(self.info()["run"]) / "whisper.json").read_text())
            )
            self.assert_reaped(self.info())
        self.assertEqual(requests[0], requests[1])
        self.assertEqual(requests[2], requests[3])
        self.assertEqual(requests[0]["at"], 2)

    def test_live_partial_record_is_retained_until_complete(self):
        p = self.run_cli(
            "--backend", "random", "--poll", ".01", GAME_MODE="partial_event"
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        run = Path(self.info()["run"])
        self.assertEqual(json.loads((run / "whisper.json").read_text())["at"], 2)
        self.assertEqual((run / "director.log").read_text(), "")
        self.assert_reaped(self.info())

    def test_normal_death_event_is_not_a_director_error(self):
        p = self.run_cli("--poll", ".01", GAME_MODE="death_event")
        self.assertEqual(p.returncode, 0, p.stderr)
        log = Path(self.info()["run"]) / "director.log"
        self.assertEqual(log.read_text(), "")

    def test_symlink_journal_fails_before_game(self):
        run = self.path / "bad-journal"
        run.mkdir(mode=0o700)
        (run / "whispers.jsonl").symlink_to(self.path / "victim")
        p = self.run_cli("--reuse-run-dir", str(run))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(self.marker.exists())

    def test_pending_pack_conflicts_rejected_with_evidence_preserved(self):
        from test_director import REQ, event

        for index, (safe, request, options) in enumerate(
            (
                (0, dict(REQ, value=2), []),
                (0, dict(REQ, id=2), []),
                (2, dict(REQ, at=1), []),
                (1, dict(REQ, at=1), []),
                (2, dict(REQ, at=1), ["--backend", "random"]),
            )
        ):
            with self.subTest(index=index):
                self.marker.unlink(missing_ok=True)
                run = self.path / f"pending-conflict-{index}"
                run.mkdir(mode=0o700)
                history = (json.dumps(event(safe=safe, turn=0)) + "\n").encode()
                mailbox = json.dumps(request).encode()
                for name, raw in (("events.jsonl", history), ("whisper.json", mailbox)):
                    (run / name).write_bytes(raw)
                    (run / name).chmod(0o600)
                result = self.run_cli("--reuse-run-dir", str(run), *options)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())
                self.assertEqual((run / "events.jsonl").read_bytes(), history)
                self.assertEqual((run / "whisper.json").read_bytes(), mailbox)

    def test_matching_future_pending_pack_and_random_restore_succeed(self):
        from test_director import REQ, event

        for index, options in enumerate(([], ["--backend", "random"])):
            run = self.path / f"pending-match-{index}"
            run.mkdir(mode=0o700)
            history = (json.dumps(event(safe=0, turn=0)) + "\n").encode()
            mailbox = json.dumps(REQ).encode()
            for name, raw in (("events.jsonl", history), ("whisper.json", mailbox)):
                (run / name).write_bytes(raw)
                (run / name).chmod(0o600)
            result = self.run_cli("--reuse-run-dir", str(run), *options)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(self.info()["mailbox"])
            self.assertEqual((run / "events.jsonl").read_bytes(), history)
            self.assertEqual((run / "whisper.json").read_bytes(), mailbox)
            self.assert_reaped(self.info())

    def test_conflicting_mailbox_arriving_before_handshake_rejected(self):
        from chaos import launcher
        from chaos.__main__ import main
        from test_director import REQ

        run = self.path / "startup-conflict"
        run.mkdir(mode=0o700)
        original_fork = launcher._fork_director
        raw = json.dumps(dict(REQ, value=2)).encode()

        def inject_conflict(*args):
            mailbox = run / "whisper.json"
            mailbox.write_bytes(raw)
            mailbox.chmod(0o600)
            return original_fork(*args)

        with (
            patch.dict(os.environ, self.env),
            patch("chaos.launcher._fork_director", side_effect=inject_conflict),
            redirect_stderr(io.StringIO()),
        ):
            result = main(
                ["play", "--game-root", str(self.root), "--reuse-run-dir", str(run)]
            )
        self.assertEqual(result, 2)
        self.assertFalse(self.marker.exists())
        self.assertEqual((run / "whisper.json").read_bytes(), raw)

    def test_incomplete_history_rejected_before_publication_or_game(self):
        from test_director import event

        complete = json.dumps(event(safe=0, turn=0)).encode()
        for index, raw in enumerate((b'{"v":1,', complete, complete + b'\n{"v":1,')):
            with self.subTest(index=index):
                self.marker.unlink(missing_ok=True)
                run = self.path / f"partial-{index}"
                run.mkdir(mode=0o700)
                log = run / "events.jsonl"
                log.write_bytes(raw)
                log.chmod(0o600)
                result = self.run_cli("--reuse-run-dir", str(run))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(self.marker.exists())
                self.assertFalse((run / "whisper.json").exists())
                self.assertEqual(log.read_bytes(), raw)

    def test_partial_history_arriving_before_handshake_rejected(self):
        from chaos import launcher
        from chaos.__main__ import main

        run = self.path / "startup-partial"
        run.mkdir(mode=0o700)
        original_fork = launcher._fork_director
        raw = b'{"v":1,'

        def inject_partial(*args):
            log = run / "events.jsonl"
            log.write_bytes(raw)
            log.chmod(0o600)
            return original_fork(*args)

        with (
            patch.dict(os.environ, self.env),
            patch("chaos.launcher._fork_director", side_effect=inject_partial),
            redirect_stderr(io.StringIO()),
        ):
            result = main(
                ["play", "--game-root", str(self.root), "--reuse-run-dir", str(run)]
            )
        self.assertEqual(result, 2)
        self.assertFalse(self.marker.exists())
        self.assertFalse((run / "whisper.json").exists())
        self.assertEqual((run / "events.jsonl").read_bytes(), raw)

    def test_wrong_uid_validation_without_privileged_chown(self):
        from chaos.__main__ import main

        run = self.path / "owned"
        run.mkdir(mode=0o700)
        # Only the unavailable chown is simulated; validation and filesystem are real.
        with (
            patch("chaos.launcher.os.getuid", return_value=os.getuid() + 1),
            redirect_stderr(io.StringIO()),
        ):
            result = main(
                ["play", "--game-root", str(self.root), "--reuse-run-dir", str(run)]
            )
        self.assertEqual(result, 2)
        self.assertFalse(self.marker.exists())

    def test_bad_options_never_start_game(self):
        cases = [
            ("--backend", "model"),
            ("--pack", "unknown"),
            ("--seed", "1"),
            ("--ordinary-food",),
            ("--backend", "random", "--pack", "ambient"),
            ("--backend", "random", "--at", "2"),
            ("--at", "0"),
            ("--id", "-1"),
            ("--max-runtime", "nan"),
            ("--max-runtime", "0"),
            ("--poll", "0"),
            ("--max-submissions", "0"),
            ("--max-events", "0"),
            ("--max-bytes", "0"),
        ]
        for args in cases:
            with self.subTest(args=args):
                p = self.run_cli(*args)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertFalse(self.marker.exists())

    def test_invalid_directories_and_executable_never_start_game(self):
        public = self.path / "public"
        public.mkdir(mode=0o755)
        private = self.path / "private"
        private.mkdir(mode=0o700)
        link = self.path / "link"
        link.symlink_to(private, target_is_directory=True)
        file = self.path / "file"
        file.touch()
        for args in [
            ("--reuse-run-dir", str(public)),
            ("--reuse-run-dir", str(link)),
            ("--reuse-run-dir", str(file)),
            ("--reuse-run-dir", str(self.path / "absent")),
            ("--run-dir", str(private)),
            ("--run-dir", str(link)),
            ("--game-root", str(file)),
            ("--game", "../elsewhere"),
            ("--game", "missing"),
        ]:
            with self.subTest(args=args):
                p = self.run_cli(*args)
                self.assertEqual(p.returncode, 2, p.stderr)
                self.assertFalse(self.marker.exists())
        self.game.chmod(0o600)
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertFalse(self.marker.exists())

    @unittest.skipUnless(os.getuid() == 0, "ownership fixture needs chown")
    def test_wrong_owner_never_starts_game(self):
        run = self.path / "foreign"
        run.mkdir(mode=0o700)
        os.chown(run, 65534, -1)
        self.assertEqual(self.run_cli("--reuse-run-dir", str(run)).returncode, 2)
        self.assertFalse(self.marker.exists())

    def test_lock_contention_fails_before_game(self):
        from chaos.director import Mailbox

        run = self.path / "busy"
        run.mkdir(mode=0o700)
        with Mailbox(run):
            p = self.run_cli("--reuse-run-dir", str(run))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(self.marker.exists())

    def test_invalid_existing_state_fails_before_game(self):
        for name in ("events.jsonl", "whisper.json"):
            run = self.path / name
            run.mkdir(mode=0o700)
            (run / name).write_text("bad state\n")
            (run / name).chmod(0o600)
            p = self.run_cli("--reuse-run-dir", str(run))
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertFalse(self.marker.exists())

    def test_preflight_schedule_failure_never_starts_game(self):
        from test_director import append, event
        from chaos.director import Mailbox

        run = self.path / "missed-schedule"
        run.mkdir(mode=0o700)
        append(run / "events.jsonl", event())
        p = self.run_cli("--reuse-run-dir", str(run))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(self.marker.exists())
        self.assertFalse((run / "director.log").exists())
        self.assertFalse((run / "whisper.json").exists())
        with Mailbox(run):
            pass

    def test_director_runtime_cap_keeps_game_and_lock_alive(self):
        from chaos.director import Mailbox

        p = self.start_waiting(
            "--backend", "random", "--max-runtime", ".05", "--poll", ".01"
        )
        info = self.info()
        time.sleep(0.15)
        self.assertIsNone(p.poll())
        with self.assertRaises(ValueError):
            Mailbox(info["run"])
        p.terminate()
        p.communicate(timeout=8)
        self.assert_reaped(info)

    def test_unresponsive_game_is_killed_and_reaped_after_signal(self):
        # Explicit Popen here allows the fixture to ignore TERM, unlike start_waiting.
        p = subprocess.Popen(
            self.command,
            cwd=ROOT,
            env=dict(self.env, GAME_MODE="ignore_term"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def cleanup():
            if p.poll() is None:
                p.terminate()
            p.communicate(timeout=8)

        self.addCleanup(cleanup)
        deadline = time.monotonic() + 5
        ignoring = Path(str(self.marker) + ".ignoring")
        while (
            not ignoring.exists() and p.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertTrue(ignoring.exists())
        info = self.info()
        p.terminate()
        p.communicate(timeout=8)
        self.assertEqual(p.returncode, -signal.SIGTERM)
        self.assertFalse(Path("/proc", str(info["pid"])).exists())
        self.assert_reaped(info)

    def test_game_exec_failure_reaps_director_and_releases_lock(self):
        self.game.write_text("#!/no/such/interpreter\n")
        run = self.path / "exec-failure"
        p = self.run_cli("--run-dir", str(run))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(self.marker.exists())
        from chaos.director import Mailbox

        with Mailbox(run):
            pass

    def test_director_death_does_not_stop_game_or_release_session_lock(self):
        p = self.run_cli(GAME_MODE="director_dies", GAME_STATUS="9")
        self.assertEqual(p.returncode, 9, p.stderr)
        self.assertTrue(Path(str(self.marker) + ".survived").exists())
        self.assert_reaped(self.info())
        self.assertIn("director", p.stderr)

    def test_supervisor_signals_forward_and_reap(self):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=sig):
                self.marker.unlink(missing_ok=True)
                p = self.start_waiting()
                info = self.info()
                p.send_signal(sig)
                p.communicate(timeout=8)
                self.assertEqual(p.returncode, -sig)
                self.assertFalse(Path("/proc", str(info["pid"])).exists())
                self.assert_reaped(info)

    def test_game_signal_status_preserved(self):
        p = self.run_cli(GAME_MODE="signal")
        self.assertEqual(p.returncode, -signal.SIGTERM, p.stderr)
        self.assert_reaped(self.info())

    def test_game_sigkill_status_preserved(self):
        p = self.run_cli(GAME_MODE="signal", GAME_SIGNAL=str(signal.SIGKILL))
        self.assertEqual(p.returncode, -signal.SIGKILL, p.stderr)
        self.assert_reaped(self.info())

    def test_game_inherits_terminal(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        p = subprocess.run(
            self.command,
            cwd=ROOT,
            env=self.env,
            stdin=slave,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(self.info()["tty"])
        self.assert_reaped(self.info())

    def test_ordinary_sets_bard_options_without_wizard_args(self):
        from chaos.ordinary_start import OPTIONS

        p = self.run_cli("--ordinary", GAME_STATUS="0")
        self.assertEqual(p.returncode, 0, p.stderr)
        info = self.info()
        self.assertEqual(info["nethackoptions"], OPTIONS)
        self.assertEqual(info["args"], [])
        self.assert_reaped(info)

    def test_ordinary_refuses_wizard_mode_before_game(self):
        p = self.run_cli("--ordinary", "--", "-D", "-u", "wizard")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
