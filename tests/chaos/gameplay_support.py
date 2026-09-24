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
import stat
import struct
import sys
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[2]
ANSI = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")


# Only the explicit suite pool owns shared inodes, never mutable build outputs.
_LINK_FALLBACK = {
    errno.EXDEV,
    errno.EPERM,
    errno.EOPNOTSUPP,
    errno.ENOSYS,
    errno.EMLINK,
}


def _asset_identity(path, *, readonly=False):
    """Hash regular files without following links or blocking on special files."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        mode = stat.S_IMODE(before.st_mode)
        if not stat.S_ISREG(before.st_mode) or mode & 0o7000:
            raise ValueError(f"not an ordinary asset: {path}")
        if readonly and mode & 0o222:
            raise ValueError(f"writable pool asset: {path}")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError(f"asset changed while hashing: {path}")
    return digest, before.st_mtime_ns, mode & ~0o222


def _install_asset(source, destination, pool):
    """Install via rename, never write/chmod through an existing case inode.

    Normal storage is one immutable snapshot per (bytes, mtime, read/exec mode)
    per suite. A filesystem without hardlinks falls back to private readonly
    copies (correctness preserved, but no per-build storage bound there).
    The pool lives under a trusted, private suite directory; it is not a global
    cache. Its assets must not be modified, including by chmod as their owner.
    """
    with tempfile.TemporaryDirectory(prefix=".asset-", dir=destination.parent) as stage:
        staged = Path(stage) / "asset"
        if pool is None:
            shutil.copy2(source, staged)
        else:
            pool.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not stat.S_ISDIR(pool.lstat().st_mode):
                raise ValueError(f"not a real asset pool directory: {pool}")
            identity = _asset_identity(source)
            digest, mtime, mode = identity
            cached = pool / f"{digest}-{mtime}-{mode:o}"
            # Temporary publication candidates are always private copies. No
            # chmod or content writes occur after any hardlink is created.
            with tempfile.TemporaryDirectory(prefix=".asset-", dir=pool) as pending:
                snapshot = cached
                if not os.path.lexists(cached):
                    candidate = Path(pending) / "asset"
                    shutil.copy2(source, candidate)
                    candidate.chmod(mode)
                    if _asset_identity(candidate, readonly=True) != identity:
                        raise ValueError(f"asset changed while copying: {source}")
                    try:
                        os.link(candidate, cached, follow_symlinks=False)
                    except FileExistsError:
                        pass  # A concurrent publisher won: validate, never clobber.
                    except OSError as exc:
                        if exc.errno not in _LINK_FALLBACK:
                            raise
                        snapshot = candidate  # No atomic link publication available.
                if _asset_identity(snapshot, readonly=True) != identity:
                    raise ValueError(f"corrupt pool asset: {snapshot}")
                try:
                    os.link(snapshot, staged, follow_symlinks=False)
                except OSError as exc:
                    if exc.errno not in _LINK_FALLBACK:
                        raise
                    shutil.copy2(snapshot, staged)
                if _asset_identity(staged, readonly=True) != identity:
                    raise ValueError(f"asset changed while installing: {snapshot}")
        os.replace(staged, destination)


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
        ordinary=False,
        *,
        asset_pool=None,
        executable=None,
    ):
        """Leave run absent for fresh launch; explicitly set launcher_fresh=False
        before a later reuse start. Never infer the mode from path existence.
        Existing run paths reject fresh construction; the launcher checks them
        again at start. Default construction and startup retain legacy reuse.
        asset_pool opts into immutable dnethack/nhdat snapshots in a private
        suite-owned directory. Use install_executable(), never overwrite those
        linked files. executable selects the initial binary without first
        copying production dnethack; existing game directories remain untouched.
        """
        if launcher_fresh and launcher_options is None:
            raise ValueError("launcher_fresh requires launcher_options")
        self.asset_pool = Path(asset_pool) if asset_pool is not None else None
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
                original = (
                    Path(executable)
                    if name == "dnethack" and executable is not None
                    else Path(source) / name
                )
                if self.asset_pool is not None and name != "license":
                    _install_asset(original, self.game / name, self.asset_pool)
                else:
                    shutil.copy2(original, self.game / name)
            for name in ("perm", "record", "logfile", "xlogfile", "livelog"):
                (self.game / name).touch()
            for name in ("save", "dumplog"):
                (self.game / name).mkdir()
        self.preload = str(preload)
        self.observe = observe
        self.wizard = wizard
        self.ordinary = ordinary
        if wizard and ordinary:
            raise ValueError("ordinary Bard start is not wizard mode")
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

    def install_executable(self, executable):
        """Atomically replace this case's binary, never mutate a shared inode."""
        _install_asset(Path(executable), self.game / "dnethack", self.asset_pool)

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

    def send(self, value, *, deadline=None):
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
        if deadline is None:
            return self.read()
        return self.read(min(3.0, max(0.0, deadline - time.monotonic())))

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
                "ordinary": self.ordinary,
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
                "options": (
                    "Bard,human,male,neutral,dog,tty,!news,!legacy,time"
                    if self.ordinary
                    else "Wizard,human,male,neutral,tty,!news,!legacy,time"
                ),
                "timezone": "UTC",
            }
        )
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(self.game)
            ordinary_options = None
            if self.ordinary:
                if str(ROOT) not in sys.path:
                    sys.path.insert(0, str(ROOT))
                from chaos.ordinary_start import OPTIONS as ordinary_options

            env = dict(
                os.environ,
                TERM="xterm",
                TZ="UTC",
                HOME=str(self.root),
                LD_PRELOAD=self.preload,
                NETHACKOPTIONS=(
                    ordinary_options
                    if self.ordinary
                    else "name:ChaosReview,role:Wizard,race:human,gender:male,align:neutral,windowtype:tty,!news,!legacy,time"
                ),
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
        # EOF/EIO can precede waitability; forty immediate reads are not an
        # exit grace period. Keep the input cap separate from elapsed time.
        deadline = time.monotonic() + 8.0
        prompts = 0
        while True:
            done, status = os.waitpid(self.pid, os.WNOHANG)
            if done:
                self.pid = None
                self.exitcode = os.waitstatus_to_exitcode(status)
                os.close(self.fd)
                self.fd = None
                self.save_artifacts()
                return self.exitcode
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if b"--More--" in text:
                response = " "
            elif b"[ynq]" in text:
                response = "n"
            else:
                response = None
            if response is not None:
                if prompts >= 40:
                    break
                prompts += 1
                text = self.send(response, deadline=deadline)
            else:
                text = self.read(min(0.2, remaining))
            if not text:
                # A closed PTY (or silent input boundary) returns immediately.
                # Yield without injecting keys, and charge this to the deadline.
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(0.01, remaining))
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
