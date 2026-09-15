"""Real terminal game driver. Artifacts and copies stay outside the source tree."""

import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import struct
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[2]
ANSI = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")


class Game:
    def __init__(
        self,
        source,
        preload,
        observe=True,
        wizard=False,
        root=None,
        echoes=True,
        launcher_options=None,
        launcher_fresh=False,
    ):
        """Leave run absent for fresh launch; explicitly set launcher_fresh=False
        before a later reuse start. Never infer the mode from path existence.
        Existing run paths reject fresh construction; the launcher checks them
        again at start. Default construction and startup retain legacy reuse.
        """
        if launcher_fresh and launcher_options is None:
            raise ValueError("launcher_fresh requires launcher_options")
        self.root = Path(root or tempfile.mkdtemp(prefix="nyarlathack-game-test-"))
        self.game = self.root / "game"
        self.run = self.root / "run"
        if launcher_fresh and os.path.lexists(self.run):
            raise FileExistsError("fresh launcher run path already exists")
        if not self.game.exists():
            self.game.mkdir(parents=True)
            if not launcher_fresh:
                self.run.mkdir(mode=0o700)
            for name in ("dnethack", "nhdat", "license"):
                shutil.copy2(Path(source) / name, self.game / name)
            for name in ("perm", "record", "logfile", "xlogfile", "livelog"):
                (self.game / name).touch()
            for name in ("save", "dumplog"):
                (self.game / name).mkdir()
        self.preload = str(preload)
        self.observe = observe
        self.wizard = wizard
        self.echoes = echoes
        self.launcher_options = launcher_options
        self.launcher_fresh = launcher_fresh
        self.pid = self.fd = None
        self.raw = bytearray()
        self.inputs = []
        self.exitcode = None
        self.sessions = []
        self._reader_pid = None
        self._input_checkpoint = None

    @staticmethod
    def _read_count(pid):
        fields = dict(
            line.split(":", 1)
            for line in Path(f"/proc/{pid}/io").read_text().splitlines()
        )
        return int(fields["rchar"])

    def _input_ready(self):
        """Observe a native stdin read, not a quiet PTY or supervisor wait.

        tty_nhgetch() flushes stdout before getchar()/read(0). This boundary
        works without CHAOS observations, including stock and restore paths.
        /proc/syscall alone also reports reads in SIGSTOPped tasks, so require
        sleeping state and an empty tty input queue. After send(), require read
        progress too: the previous read may still be asleep while the PTY line
        discipline is delivering the newly written bytes.
        """
        assert self.fd is not None
        read_syscall = {"x86_64": "0", "aarch64": "63"}.get(os.uname().machine)
        if read_syscall is None:
            raise AssertionError("input readiness: unsupported Linux syscall ABI")
        pending = [self.pid]
        while pending:
            pid = pending.pop()
            proc = Path(f"/proc/{pid}")
            try:
                pending.extend(
                    map(int, (proc / f"task/{pid}/children").read_text().split())
                )
                if not (proc / "exe").samefile(self.game / "dnethack"):
                    continue
                if self._input_checkpoint is not None:
                    reader, count = self._input_checkpoint
                    if pid != reader or self._read_count(pid) < count:
                        continue
                # Establish consumption before sampling the current read: an old
                # read(0) plus later rchar progress can otherwise hide a pipe wait.
                call = (proc / "syscall").read_text().split()
                state = (proc / "stat").read_text().rsplit(")", 1)[1].split()[0]
                if state != "S" or call[:2] != [read_syscall, "0x0"]:
                    continue
                # Open only during the check; retaining a slave fd hides EOF.
                fd = os.open(proc / "fd/0", os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
                try:
                    # Linux TIOCGPTPEER (_IO('T', 0x41)) opens this master's
                    # actual slave, without guessing names across devpts mounts.
                    peer = fcntl.ioctl(
                        self.fd,
                        0x5441,
                        os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC,
                    )
                    try:
                        same_terminal = os.path.samestat(os.fstat(fd), os.fstat(peer))
                    finally:
                        os.close(peer)
                    if not same_terminal:
                        continue
                    queued = fcntl.ioctl(fd, termios.FIONREAD, struct.pack("i", 0))
                    if not os.isatty(fd) or struct.unpack("i", queued)[0]:
                        continue
                finally:
                    os.close(fd)
                self._reader_pid = pid
                return True
            except (FileNotFoundError, ProcessLookupError):
                # fork/exec/exit can race the proc walk; retry until the deadline.
                continue
            except PermissionError as exc:
                # Exiting tasks can lose their mm between exe and syscall reads.
                # Let PTY EOF win that race; persistent denial still fails closed.
                self._readiness_error = "readable Linux /proc required: " + str(exc)
        return False

    def read(self, initial=3.0):
        assert self.fd is not None and self.pid is not None
        self._readiness_error = "game is not blocked reading terminal stdin"
        data = bytearray()
        deadline = time.monotonic() + initial
        try:
            while time.monotonic() < deadline:
                if select.select([self.fd], [], [], 0)[0]:
                    try:
                        part = os.read(self.fd, 65536)
                    except OSError as exc:
                        if exc.errno == errno.EIO:  # Linux PTY slave closed.
                            break
                        raise
                    if not part:
                        break
                    data.extend(part)
                    if len(data) > 1000000:
                        raise AssertionError("terminal output exceeded limit")
                    continue
                if self._input_ready():
                    # Output can arrive between the drain and the proc snapshot.
                    # Once the game is waiting for input, drain its final flush.
                    if select.select([self.fd], [], [], 0)[0]:
                        continue
                    break
                select.select(
                    [self.fd], [], [], min(0.01, max(0, deadline - time.monotonic()))
                )
            else:
                raise AssertionError(
                    "terminal input readiness timed out ("
                    + self._readiness_error
                    + "): "
                    + repr(bytes(data[-500:]))
                )
        finally:
            self.raw.extend(data)
        return ANSI.sub(b"", bytes(data))

    def send(self, value):
        assert self.fd is not None
        if isinstance(value, str):
            value = value.encode()
        if self._reader_pid is not None:
            self._input_checkpoint = (
                self._reader_pid,
                self._read_count(self._reader_pid) + len(value),
            )
        self.inputs.append(value.hex())
        os.write(self.fd, value)
        return self.read()

    def more(self, text):
        for _ in range(30):
            if b"--More--" not in text:
                return text
            text = self.send(" ")
        raise AssertionError("paging exceeded limit")

    def start(self):
        assert self.pid is None
        if self.launcher_fresh and self.launcher_options is None:
            raise ValueError("launcher_fresh requires launcher_options")
        self._reader_pid = None
        self._input_checkpoint = None
        self.sessions.append(
            {
                "wizard": self.wizard,
                "observe": self.observe,
                "echoes": self.echoes,
                "haunting_source_sha256": hashlib.sha256(
                    (self.run / "haunting.lua").read_bytes()
                ).hexdigest()
                if (self.run / "haunting.lua").exists()
                else None,
                "terminal": [24, 80],
                "inputs_begin": len(self.inputs),
                "sha256": {
                    name: hashlib.sha256((self.game / name).read_bytes()).hexdigest()
                    for name in ("dnethack", "nhdat")
                },
                "clock_sha256": hashlib.sha256(
                    Path(self.preload).read_bytes()
                ).hexdigest(),
                "options": "Wizard,human,male,neutral,tty,!news,!legacy,time",
                "timezone": "UTC",
            }
        )
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.game)
            env = dict(
                os.environ,
                TERM="xterm",
                TZ="UTC",
                HOME=str(self.root),
                LD_PRELOAD=self.preload,
                NETHACKOPTIONS="name:ChaosReview,role:Wizard,race:human,gender:male,align:neutral,windowtype:tty,!news,!legacy,time",
            )
            env.pop("NYARLATHACK_RUN_DIR", None)
            env["NYARLATHACK_ECHOES"] = "1" if self.echoes else "0"
            if self.observe:
                env["NYARLATHACK_RUN_DIR"] = str(self.run)
            args = ["./dnethack"] + (["-D", "-u", "wizard"] if self.wizard else [])
            if self.launcher_options is not None:
                env["PYTHONPATH"] = str(ROOT)
                args = [
                    sys.executable,
                    "-m",
                    "chaos",
                    "play",
                    "--run-dir" if self.launcher_fresh else "--reuse-run-dir",
                    str(self.run),
                    "--game-root",
                    str(self.game),
                    *self.launcher_options,
                    "--",
                    *args[1:],
                ]
                os.execve(sys.executable, args, env)
            os.execve("./dnethack", args, env)
        self.pid, self.fd = pid, fd
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        text = self.read(3)
        for _ in range(30):
            if b"No past inheritance" in text:
                text = self.send("n")
            elif b"--More--" in text:
                text = self.send(" ")
            elif b"keep the save file" in text.lower():
                text = self.send("n")
            elif b"Delete the old file?" in text:
                text = self.send("n")
            else:
                break
        return text

    def events(self):
        p = self.run / "events.jsonl"
        return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []

    def request(self, kind, ident, at, duration=5):
        value, telegraph = (
            (1, 1)
            if kind == "ambient"
            else (50, 2)
            if kind == "ward_efficacy"
            else (2, 3)
        )
        r = dict(
            v=1,
            id=ident,
            mutation=kind,
            value=value,
            duration=0 if kind == "ambient" else duration,
            telegraph=telegraph,
            at=at,
        )
        p = self.run / "whisper.tmp"
        p.write_text(json.dumps(r))
        p.chmod(0o600)
        p.replace(self.run / "whisper.json")
        return r

    def sanity(self, value):
        text = self.send("#setsanity\n")
        assert b"Set your sanity to what?" in text, text
        return self.more(self.send(str(value) + "\n"))

    def wait_turns(self, count):
        for _ in range(count):
            self.more(self.send("."))

    def finish(self, text):
        assert self.pid is not None and self.fd is not None
        for _ in range(40):
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.pid = None
                self.exitcode = os.waitstatus_to_exitcode(status)
                os.close(self.fd)
                self.fd = None
                self.save_artifacts()
                return self.exitcode
            if b"--More--" in text:
                text = self.send(" ")
            elif b"[ynq]" in text:
                text = self.send("n")
            else:
                text = self.read(0.2)
        raise AssertionError("game failed to exit: " + repr(text[-500:]))

    def quit(self):
        text = self.send("#quit\n")
        assert b"Really quit?" in text, text
        return self.finish(self.send("y"))

    def save(self):
        text = self.send("#save\n")
        if b"[yn]" in text or b"Save the game?" in text:
            text = self.send("y")
        return self.finish(text)

    def save_artifacts(self):
        (self.root / "terminal.raw").write_bytes(self.raw)
        (self.root / "inputs.json").write_text(json.dumps(self.inputs))
        (self.root / "manifest.json").write_text(
            json.dumps({"sessions": self.sessions, "exit": self.exitcode}, indent=2)
        )

    def close(self):
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except ProcessLookupError:
                pass
            self.pid = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.save_artifacts()
