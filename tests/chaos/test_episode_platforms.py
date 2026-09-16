#!/usr/bin/python3
"""Opt-in real curses + bounded CHAOS=0 no-whisper TTY comparison.

External fixture sources are measured separately; helpers/headers/objects come
only from the explicitly selected, calibrated source build. No action purity or
full-game equivalence is claimed. Never call Game.close on an uncertain child.
"""

import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import resource
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import unittest

LIMIT = 1_000_000


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


class Cancellation:
    """Catchable cancellation only: never raise between acquisition and bookkeeping.

    The single-threaded driver has no other reaper. Children inherit no blocked
    signals; exec resets these handlers. SIGKILL/host failure are out of scope.
    """

    def __init__(self):
        self.signum = None

    def handler(self, signum, _frame):
        if self.signum is None:
            self.signum = signum

    def checkpoint(self):
        if self.signum is not None:
            raise TimeoutError("platform supervisor signal " + str(self.signum))


def observe(pid):
    """Prove direct-child ownership without releasing the PID/PGID pin."""
    try:
        return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except ChildProcessError as exc:
        raise RuntimeError("lost unreaped child ownership: " + str(pid)) from exc


def terminate(pid):
    """TERM, grace, KILL the pinned session group, THEN reap its leader.

    Never return early on leader exit: descendants may ignore TERM and retain
    pipes. No poll(), wait(), context-manager exit, or other reaper may run
    before this function. An ECHILD fails closed, before any group signal.
    """
    observe(pid)
    # forkpty may return in the parent just before the child establishes its
    # session. Wait for that boundary; never signal the parent's shared group.
    deadline = time.monotonic() + 2
    while os.getpgid(pid) != pid or os.getsid(pid) != pid:
        if observe(pid) is not None or time.monotonic() >= deadline:
            raise RuntimeError("owned child did not establish isolated session")
        time.sleep(0.01)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        observe(pid)
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass
        if sig == signal.SIGTERM:
            # Deliberately retain even a zombie leader throughout the grace.
            time.sleep(0.1)
    deadline = time.monotonic() + 2
    while observe(pid) is None:
        if time.monotonic() >= deadline:
            raise RuntimeError("owned child did not exit after KILL: " + str(pid))
        time.sleep(0.01)
    done, status = os.waitpid(pid, os.WNOHANG)
    if done != pid:
        raise RuntimeError("owned child did not reap: " + str(pid))
    return os.waitstatus_to_exitcode(status)


def cleanup_errors(errors, original):
    if errors:
        message = "platform cleanup: " + "; ".join(errors)
        if original is not None:
            original.add_note(message)
        else:
            raise RuntimeError(message)


def owned_game_type(base, cancel):
    """Keep pinned helper startup/input semantics, replace only supervision."""

    class OwnedGame(base):
        def read(self, initial=3.0):
            # base.start has assigned both fork results before this checkpoint.
            cancel.checkpoint()
            if self.pid is not None:
                observe(self.pid)
                save(
                    self.root / "owned-process.json",
                    {"pid": self.pid, "pgid": os.getpgid(self.pid)},
                )
            text = super().read(initial)
            cancel.checkpoint()
            assert len(self.raw) <= LIMIT, "total terminal/diagnostic cap"
            return text

        def finish(self, text):
            assert self.pid is not None and self.fd is not None
            try:
                for _ in range(40):
                    cancel.checkpoint()
                    if observe(self.pid) is not None:
                        break
                    if b"--More--" in text:
                        text = self.send(" ")
                    elif b"[ynq]" in text:
                        text = self.send("n")
                    else:
                        text = self.read(0.2)
                else:
                    raise AssertionError("game failed to exit: " + repr(text[-500:]))
            finally:
                self.cleanup()
            cancel.checkpoint()
            return self.exitcode

        def cleanup(self):
            original = sys.exc_info()[1]
            errors = []
            if self.pid is not None:
                try:
                    self.exitcode = terminate(self.pid)
                    self.pid = None
                except Exception as exc:
                    errors.append(repr(exc))
            if self.fd is not None:
                fd, self.fd = self.fd, None
                try:
                    os.close(fd)
                except OSError as exc:
                    errors.append(repr(exc))
            # Publishing errors must not prevent descriptor closure or the other
            # independent evidence attempt. Keep the triggering exception.
            for publish in (
                self.save_artifacts,
                lambda: save(
                    self.root / "cleanup.json",
                    {"pid": self.pid, "returncode": self.exitcode, "errors": errors},
                ),
            ):
                try:
                    publish()
                except Exception as exc:
                    errors.append(repr(exc))
            cleanup_errors(errors, original)

    return OwnedGame


def bounded(command, work, env, prefix, timeout=45, terminal=False, cancel=None):
    """Drain terminal AND diagnostics with caps, retain evidence even on failure."""
    save(prefix.with_suffix(".command.json"), list(map(str, command)))
    master = slave = None
    process = None
    streams = {}
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    cancel = cancel or Cancellation()
    cancel.checkpoint()
    try:
        if terminal:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        process = subprocess.Popen(
            list(map(str, command)),
            cwd=work,
            env=env,
            stdin=slave if terminal else subprocess.DEVNULL,
            stdout=slave if terminal else subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        if slave is not None:
            os.close(slave)
            slave = None
        streams[master if terminal else process.stdout.fileno()] = "stdout"
        streams[process.stderr.fileno()] = "stderr"
        deadline = time.monotonic() + timeout
        while streams:
            cancel.checkpoint()
            if time.monotonic() >= deadline:
                raise TimeoutError("bounded command timed out; no speculative input")
            for fd in select.select(list(streams), [], [], 0.05)[0]:
                try:
                    part = os.read(fd, 65536)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    part = b""
                key = streams[fd]
                if not part:
                    del streams[fd]
                    continue
                captured[key].extend(part)
                if len(captured[key]) > LIMIT:
                    raise AssertionError(key + " exceeded capture limit")
        while observe(process.pid) is None:
            cancel.checkpoint()
            if time.monotonic() >= deadline:
                raise TimeoutError("bounded command exit timed out")
            time.sleep(0.01)
        process.returncode = terminate(process.pid)
        cancel.checkpoint()
        assert process.returncode == 0, (command, process.returncode)
        return bytes(captured["stdout"]), bytes(captured["stderr"])
    finally:
        original = sys.exc_info()[1]
        errors = []
        try:
            if process is not None and process.returncode is None:
                process.returncode = terminate(process.pid)
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            # Close resources independently of cleanup/publication failures.
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        try:
                            stream.close()
                        except OSError as exc:
                            errors.append(repr(exc))
            for fd in (master, slave):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError as exc:
                        errors.append(repr(exc))
            for key, data in captured.items():
                try:
                    prefix.with_suffix("." + key).write_bytes(data)
                except OSError as exc:
                    errors.append(repr(exc))
            try:
                save(
                    prefix.with_suffix(".status.json"),
                    {
                        "returncode": None if process is None else process.returncode,
                        "inputs": [],
                        "failure": None if original is None else repr(original),
                        "cleanup": {"errors": errors},
                    },
                )
            except OSError as exc:
                errors.append(repr(exc))
            cleanup_errors(errors, original)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "receipt", "revision", "artifacts", "off-tuple"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("revision must already be full lowercase 40hex")
    for name in ("root", "receipt", "artifacts", "off_tuple"):
        value = getattr(args, name)
        path = Path(value)
        if not path.is_absolute() or str(path) != value or path.resolve() != path:
            raise ValueError("explicit canonical absolute path required: " + name)
    root, receipt, out, off = map(
        Path, (args.root, args.receipt, args.artifacts, args.off_tuple)
    )
    if Path.cwd() != root:
        raise ValueError("launch from selected trusted checkout root")
    if not out.is_relative_to(Path("/tmp")) or out.is_relative_to(root):
        raise ValueError("artifacts must be outside checkout, under /tmp")
    trusted = root / "tests/chaos"
    helper_names = (
        "gameplay_support",
        "native_fixture_selection",
        "native_rng",
        "native_build_calibration",
        "native_build_identity",
    )
    for name in helper_names:
        cached = sys.modules.get(name)
        if cached is not None:
            origin = getattr(cached, "__file__", None)
            if origin is None or Path(origin).resolve().parent != trusted:
                raise ValueError("unexpected cached verifier path")
    sys.path.insert(0, str(trusted))
    import gameplay_support
    import native_fixture_selection
    import native_rng  # noqa: F401 -- same complete trusted helper guard

    for name in helper_names:
        module = sys.modules[name]
        if module.__file__ is None or Path(module.__file__).resolve().parent != trusted:
            raise ValueError("unexpected imported verifier path")
    if gameplay_support.ROOT != root:
        raise ValueError("selected root is not actual gameplay_support.ROOT")
    selection_env = dict(
        os.environ,
        NYARLATHACK_NATIVE_FIXTURE_MODE="source-build",
        NYARLATHACK_NATIVE_BUILD_RECEIPT=str(receipt),
        NYARLATHACK_NATIVE_EXPECTED_REVISION=args.revision,
    )
    selection = native_fixture_selection.prepare(root, selection_env)
    if selection.environment is None:
        raise ValueError("source-build isolated environment required")
    # Off provenance is tuple-only, explicitly NOT an off-object calibration.
    off_manifest = json.loads((receipt / "0-manifest.json").read_text())
    off_commands = json.loads((receipt / "0-commands.json").read_text())
    if (
        off_manifest["revision"] != args.revision
        or type(off_manifest["mode"]) is not int
        or off_manifest["mode"] != 0
    ):
        raise ValueError("off manifest identity mismatch")
    if off_manifest["commands"] != off_commands:
        raise ValueError("off command receipts differ")
    for record, action in zip(off_commands, ("clean", "install"), strict=True):
        if record["exit_code"] != 0 or record["argv"] != [
            "/usr/bin/make",
            "-j2",
            action,
            "CHAOS=0",
            "CC=/usr/bin/cc",
            "PKG_CONFIG=/usr/bin/pkg-config",
        ]:
            raise ValueError("off build was not successful mode 0")

    def check_off(directory):
        for name in ("dnethack", "nhdat", "license"):
            path = directory / name
            expected = off_manifest["pairs"][name]
            if (
                path.is_symlink()
                or digest(path) != expected["sha256"]
                or path.stat().st_size != expected["size"]
            ):
                raise ValueError("off tuple hash mismatch: " + name)

    check_off(off)
    os.umask(0o077)
    out.mkdir(mode=0o700, exist_ok=False)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    env = dict(
        selection.environment,
        HOME=str(out),
        TMPDIR=str(out),
        MAIL=str(out / "private-mail"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    (out / "private-mail").write_bytes(b"")
    save(
        out / "off-provenance.json",
        {
            "tuple": str(off),
            "manifest": off_manifest,
            "commands": off_commands,
            "manifest_sha256": digest(receipt / "0-manifest.json"),
            "commands_sha256": digest(receipt / "0-commands.json"),
        },
    )
    objects = (
        sorted((root / "src").glob("*.o"))
        + [
            root / p
            for p in (
                "sys/unix/unixres.o",
                "sys/unix/unixunix.o",
                "sys/unix/unixmain.o",
                "sys/share/ioctl.o",
                "sys/share/unixtty.o",
            )
        ]
        + sorted((root / "win/tty").glob("*.o"))
        + sorted((root / "win/curses").glob("*.o"))
    )
    originals = {str(p): digest(p) for p in objects}
    manifest = json.loads((receipt / "1-manifest.json").read_text())
    all_originals = {
        str(root / name): digest(root / name) for name in manifest["objects"]
    }
    save(out / "original-object-hashes.json", originals)
    save(out / "manifest-object-hashes.json", all_originals)
    active = []

    cancel = Cancellation()
    handlers = {
        s: signal.signal(s, cancel.handler)
        for s in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM)
    }
    signal.alarm(180)
    try:

        def run(command, name, timeout=45):
            return bounded(command, out, env, out / name, timeout, cancel=cancel)[0]

        for name in native_fixture_selection.ORACLE_SOURCES:
            shutil.copyfile(root / name, out / Path(name).name)
        selection.verify_helper_copy(out)
        flags = [
            "-std=gnu17",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-DCHAOS",
            "-DDLB",
            "-isystem" + str(root / "include"),
        ]
        run(
            [
                selection.compiler,
                *flags,
                out / "curio_save_layout.c",
                "-o",
                out / "layout",
            ],
            "layout-build",
        )
        selection.validate_schema(json.loads(run([out / "layout"], "layout", 10)))
        save(out / "selection.json", selection.record())
        source = Path(__file__).resolve().with_name("episode_platforms.c")
        for path in (source, Path(__file__).resolve(), trusted / "replay_clock.c"):
            shutil.copyfile(path, out / path.name)
        save(
            out / "fixture-hashes.json",
            {
                p.name: digest(p)
                for p in (source, Path(__file__).resolve(), trusted / "replay_clock.c")
            },
        )
        run(
            [
                "/usr/bin/objcopy",
                "--redefine-sym",
                "main=original_game_main",
                root / "sys/unix/unixmain.o",
                out / "unixmain.o",
            ],
            "rename-main",
            15,
        )
        linked = [
            out / "unixmain.o" if p == root / "sys/unix/unixmain.o" else p
            for p in objects
        ]
        run(
            [
                selection.compiler,
                *flags,
                "-c",
                out / source.name,
                "-o",
                out / "fixture.o",
            ],
            "fixture-compile",
        )
        libs = (
            run(["/usr/bin/pkg-config", "--libs", "lua5.4"], "lua-libs", 10)
            .decode()
            .split()
        )
        exe = out / "episode-platforms"
        run(
            [
                selection.compiler,
                out / "fixture.o",
                *linked,
                "-lncursesw",
                "-ltinfo",
                "-lm",
                *libs,
                "-o",
                exe,
            ],
            "fixture-link",
            60,
        )
        clock = out / "clock.so"
        run(
            [
                selection.compiler,
                "-shared",
                "-fPIC",
                "-Wall",
                "-Wextra",
                "-Werror",
                out / "replay_clock.c",
                "-ldl",
                "-o",
                clock,
            ],
            "clock-build",
            30,
        )
        again = native_fixture_selection.prepare(root, selection_env)
        if again.record()["source_build"] != selection.record()["source_build"]:
            raise ValueError("source build changed during fixture link")
        assert originals == {p: digest(Path(p)) for p in originals}
        save(out / "executable-hashes.json", {str(p): digest(p) for p in (exe, clock)})
        renders = []
        for enabled in (False, True):
            work = out / ("curses-on" if enabled else "curses-off")
            g = gameplay_support.Game(selection.tuple_dir, clock, root=work)
            selection.verify_copy(g.game)
            options = work / "options"
            options.write_text("OPTIONS=!splash_screen,!perm_invent,windowborders:2\n")
            child_env = dict(
                env,
                HOME=str(work),
                TERM="xterm",
                LINES="24",
                COLUMNS="80",
                NETHACKOPTIONS="@" + str(options),
                NYARLATHACK_RUN_DIR=str(g.run),
                NYARLATHACK_OBSERVATIONS=str(int(enabled)),
            )
            raw, diagnostic = bounded(
                [exe], g.game, child_env, work / "terminal", 20, True, cancel=cancel
            )
            assert raw.count(b"You produce a high whistling sound.") == 1
            assert raw.count(b"You listen.") == 1
            state = json.loads(diagnostic)
            assert state["port"] == "curses" and state["pending"] == 0
            records = g.events()
            assert not any(e["event"] == "ack" for e in records)
            observations = [e for e in records if e["v"] == 2]
            if enabled:
                assert [e["observation"]["stage"] for e in observations] == [
                    "enabled",
                    "started",
                    "completed",
                ]
                start, end = observations[1:]
                assert start["seq"] == state["root"] == end["observation"]["root_seq"]
                assert start["observation"]["root_seq"] == 0
            else:
                assert records and not observations and state["root"] == 0
            renders.append((raw, {k: v for k, v in state.items() if k != "root"}))
        assert renders[0] == renders[1]
        save(
            out / "curses-result.json",
            {
                "passed": True,
                "processes": 2,
                "raw_bytes": len(renders[0][0]),
                "inputs": [],
            },
        )

        BoundedGame = owned_game_type(gameplay_support.Game, cancel)

        games = []
        variants = [
            ("stock-chaos0", off, False, False),
            ("inactive", selection.tuple_dir, False, False),
            ("legacy-empty", selection.tuple_dir, True, False),
            ("legacy-repeat", selection.tuple_dir, True, False),
            ("v2-empty", selection.tuple_dir, True, True),
            ("v2-repeat", selection.tuple_dir, True, True),
        ]
        for name, source_tuple, observe, v2 in variants:
            g = BoundedGame(source_tuple, clock, observe=observe, root=out / name)
            active.append(g)
            if source_tuple == off:
                check_off(g.game)
            else:
                selection.verify_copy(g.game)
            if not observe:
                g.run.rmdir()  # private, newly created empty directory only
            old_env = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env)
                if v2:
                    os.environ["NYARLATHACK_OBSERVATIONS"] = "1"
                else:
                    os.environ.pop("NYARLATHACK_OBSERVATIONS", None)
                g.start()
            finally:
                os.environ.clear()
                os.environ.update(old_env)
            g.wait_turns(12)
            assert g.quit() == 0
            g.save_artifacts()
            games.append(g)
            if not observe:
                assert not g.run.exists()
            else:
                events = g.events()
                assert events and not any(e["event"] == "ack" for e in events)
                assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
                obs = [e for e in events if e["v"] == 2]
                if v2:
                    assert obs == [events[0]] and events[1]["event"] == "session"
                    assert obs[0]["observation"] == {
                        "operation": "none",
                        "stage": "enabled",
                        "root_seq": 0,
                        "fact": "none",
                    }
                else:
                    assert not obs and events[0]["event"] == "session"
                # chaos_io_open creates the empty journal even with no request.
                assert (g.run / "whispers.jsonl").read_bytes() == b""
                assert not (g.run / "whisper.json").exists()
                assert not (g.run / "whisper.tmp").exists()
        for g in games[1:]:
            assert g.inputs == games[0].inputs, "input parity"
            assert g.raw == games[0].raw, "raw terminal parity: " + g.root.name
            assert (g.game / "xlogfile").read_bytes() == (
                games[0].game / "xlogfile"
            ).read_bytes(), "xlog parity"
        for a, b in ((2, 3), (4, 5)):
            assert (games[a].run / "events.jsonl").read_bytes() == (
                games[b].run / "events.jsonl"
            ).read_bytes(), "repeat event bytes"
        save(
            out / "result.json",
            {
                "passed": True,
                "curses_processes": 2,
                "tty_variants": [g.root.name for g in games],
                "tty_raw_bytes": len(games[0].raw),
                "limits": "synthetic curses scope and bounded no-whisper transcript, not selected-action acceptance",
            },
        )
        print("PLATFORM_ARTIFACTS=" + str(out))
    finally:
        signal.alarm(0)
        original = sys.exc_info()[1]
        errors = []
        try:
            for g in active:
                try:
                    g.cleanup()
                except Exception as exc:
                    errors.append(repr(exc))
        finally:
            try:
                after = {p: digest(Path(p)) for p in all_originals}
                save(out / "manifest-object-hashes-after.json", after)
                assert after == all_originals, "native originals changed"
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
        cleanup_errors(errors, original)
    cancel.checkpoint()


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "opt-in actual game tests"
)
class EpisodePlatformTests(unittest.TestCase):
    def test_explicit_source_platforms(self):
        """Explicit parameters prevent implicit archived or working-tree fallback."""
        keys = ("ROOT", "RECEIPT", "REVISION", "ARTIFACTS", "OFF_TUPLE")
        args = []
        for key in keys:
            value = os.environ.get("NYARLATHACK_PLATFORM_" + key)
            self.assertIsNotNone(value, "set NYARLATHACK_PLATFORM_" + key)
            args.extend(["--" + key.lower().replace("_", "-"), value])
        main(args)


if __name__ == "__main__":
    main()
