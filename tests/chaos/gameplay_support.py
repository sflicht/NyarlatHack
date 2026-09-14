"""Real terminal game driver. Artifacts and copies stay outside the source tree."""

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
    ):
        self.root = Path(root or tempfile.mkdtemp(prefix="nyarlathack-game-test-"))
        self.game = self.root / "game"
        self.run = self.root / "run"
        if not self.game.exists():
            self.game.mkdir(parents=True)
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
        self.pid = self.fd = None
        self.raw = bytearray()
        self.inputs = []
        self.exitcode = None
        self.sessions = []

    def read(self, initial=1.0):
        assert self.fd is not None
        data = bytearray()
        deadline = time.monotonic() + initial
        while time.monotonic() < deadline:
            if not select.select(
                [self.fd], [], [], max(0, deadline - time.monotonic())
            )[0]:
                break
            try:
                part = os.read(self.fd, 65536)
            except OSError:
                break
            if not part:
                break
            data.extend(part)
            deadline = time.monotonic() + 0.10
            if len(data) > 1000000:
                raise AssertionError("terminal output exceeded limit")
        self.raw.extend(data)
        return ANSI.sub(b"", bytes(data))

    def send(self, value):
        assert self.fd is not None
        if isinstance(value, str):
            value = value.encode()
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
                    "--reuse-run-dir",
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
