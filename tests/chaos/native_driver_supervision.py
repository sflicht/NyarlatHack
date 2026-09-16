"""Linux test-support launcher, separate from frozen native provenance helpers.

Only the external, single-threaded supervisor becomes a subreaper. It is the
exclusive reaper; waitid(WNOWAIT) pins identities until all owned descendants
have exited. Normal forkpty/setsid descendants are included through adoption.
SIGKILL of this supervisor, hostile daemons, stuck kernel tasks, and blocking
filesystem operations are outside the bounded-containment contract.
"""

from contextlib import ExitStack
import ctypes
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time


def run_driver(
    script, args, root, artifacts, *, timeout=220, term_grace=5, limit=1048576
):
    """Keep suite resources/signals/environment unchanged; return code and logs."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError(
            "run_driver requires the main thread for cancellation safety"
        )
    artifacts = Path(artifacts)
    parent = artifacts.parent
    if parent.stat().st_mode & 0o077:
        raise ValueError("driver invocation parent must be private")
    if os.path.lexists(artifacts):
        raise ValueError("artifact leaf must be absent")
    logs = Path(tempfile.mkdtemp(prefix=artifacts.name + ".driver-", dir=parent))
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("NYARLATHACK_OBSERVATIONS", None)
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        str(logs),
        str(timeout),
        str(term_grace),
        str(limit),
        sys.executable,
        str(script),
        *args,
    ]
    # Python handlers must not raise between Popen creating a child and handing
    # us its identity. Defer cancellation through acquisition AND final reap.
    saved = {
        sig: signal.getsignal(sig)
        for sig in signal.valid_signals()
        if sig in (signal.SIGINT, signal.SIGTERM, signal.SIGALRM)
        or callable(signal.getsignal(sig))
    }
    cancelled = []
    installed = []
    process = None
    code = 125
    original = None

    def defer(signum, frame):
        if not cancelled:
            cancelled.append(signum)

    def checkpoint():
        if cancelled:
            if cancelled[0] == signal.SIGINT:
                raise KeyboardInterrupt("driver parent cancellation")
            raise InterruptedError(f"driver parent signal {cancelled[0]}")

    try:
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, saved)
        try:
            for sig in saved:
                installed.append(sig)
                signal.signal(sig, defer)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        process = subprocess.Popen(
            command,
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout + term_grace + 10
        while True:
            checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout + term_grace + 10)
            try:
                code = process.wait(timeout=min(0.05, remaining))
                checkpoint()
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException as exc:
        original = exc
        original.add_note(f"driver diagnostics retained at {logs}")
        if process is not None:
            errors = []
            reaped = False
            try:
                process.terminate()
            except BaseException as secondary:
                errors.append(f"TERM: {secondary!r}")
            try:
                process.wait(timeout=term_grace + 5)
                reaped = True
            except BaseException as secondary:
                errors.append(f"grace wait: {secondary!r}")
            if not reaped:
                # Killing the supervisor cannot prove descendant containment.
                errors.append("forced supervisor escalation")
                try:
                    process.kill()
                except BaseException as secondary:
                    errors.append(f"KILL: {secondary!r}")
                try:
                    process.wait(timeout=2)
                    reaped = True
                except BaseException as secondary:
                    errors.append(f"final reap: {secondary!r}")
            if reaped and not _verified_status(logs, process.returncode):
                errors.append("missing, invalid, or failed family cleanup status")
            if errors:
                original.add_note(
                    "descendant containment unverified; " + "; ".join(errors)
                )
    finally:
        # Block delivery during restoration. Unblocking can invoke an original
        # handler, so preserve the first exception even at that last boundary.
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, installed)
        try:
            for sig in installed:
                try:
                    signal.signal(sig, saved[sig])
                except BaseException as secondary:
                    if original is None:
                        original = secondary
                        original.add_note(f"driver diagnostics retained at {logs}")
                    else:
                        original.add_note(f"signal restoration: {secondary!r}")
                    # Retry a transient setter failure, but never abandon the
                    # remaining handlers or the mask if restoration fails.
                    try:
                        signal.signal(sig, saved[sig])
                    except BaseException as retry_error:
                        original.add_note(f"signal restoration retry: {retry_error!r}")
        finally:
            try:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
            except BaseException as secondary:
                if original is None:
                    original = secondary
                    original.add_note(f"driver diagnostics retained at {logs}")
                else:
                    original.add_note(f"signal restoration: {secondary!r}")
    if original is not None:
        raise original
    try:
        checkpoint()
    except BaseException as exc:
        exc.add_note(f"driver diagnostics retained at {logs}")
        raise
    if code == 0 and not _verified_status(logs, code):
        code = 125
    return code, logs


def _verified_status(logs, code):
    """Bounded diagnostic consistency check, not same-UID authentication."""
    try:
        fd = os.open(
            logs / "supervisor.status.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        )
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                return False
            data = os.read(fd, 65537)
        finally:
            os.close(fd)
        if len(data) > 65536:
            return False
        status = json.loads(data)
        return (
            isinstance(status, dict)
            and status.get("family_cleanup") == "verified"
            and "cleanup" in status
            and status["cleanup"] is None
            and status.get("close_errors") == []
            and status.get("publication_errors") == []
            and type(status.get("returncode")) is int
            and status["returncode"] == code
            and "failure" in status
            and (status["failure"] is None or isinstance(status["failure"], str))
            and (code != 0 or status["failure"] is None)
        )
    except (OSError, ValueError, RecursionError):
        return False


def observation(pid):
    """Successful waitid, even None, proves unreaped direct-child ownership."""
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)


def owned_children():
    # Single-threaded process: never scan the host process table or trust names.
    return [
        int(p)
        for p in Path("/proc/self/task/" + str(os.getpid()) + "/children")
        .read_text()
        .split()
    ]


def owned_signal(pid, sig):
    observation(pid)  # ECHILD fails closed BEFORE either signal.
    # A session leader's unreaped identity also pins its group. Nonleaders are
    # signalled individually; adoption exposes further descendants on next pass.
    if os.getpgid(pid) == pid and os.getsid(pid) == pid:
        os.killpg(pid, sig)
    else:
        os.kill(pid, sig)


def cleanup(pid, grace, pump):
    """Ask the driver to clean known Games, then kill/reap only owned children."""
    errors = []
    try:
        owned_signal(pid, signal.SIGTERM)
    except Exception as exc:
        errors.append(repr(exc))
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        pump()
    deadline = time.monotonic() + 2
    while True:
        children = owned_children()
        for child in children:
            try:
                owned_signal(child, signal.SIGKILL)
            except Exception as exc:
                errors.append(repr(exc))
        # Do not reap ANY leader until every owned child is waitable. Exiting
        # parents have already handed their children to this subreaper then.
        states = {child: observation(child) for child in children}
        if all(states.values()) and set(owned_children()) == set(children):
            for child in children:
                os.waitpid(child, os.WNOHANG)
            if owned_children():
                raise RuntimeError("unexpected children after final reap")
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("owned descendant cleanup deadline; " + repr(errors))
        pump()
    if errors:
        raise RuntimeError("owned cleanup errors: " + repr(errors))


def supervise(logs, timeout, grace, limit, command):
    """Publish failures independently of driver capture and buffered closure."""
    status = {
        "failure": None,
        "cleanup": None,
        "family_cleanup": "unverified",
        "returncode": 125,
        "truncated": {},
        "close_errors": [],
        "publication_errors": [],
    }
    fallback = None
    code = 125
    try:
        fallback = os.open(
            logs / "supervisor.fallback.log",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except OSError as exc:
        status["publication_errors"].append(f"fallback open: {exc!r}"[:4096])
    try:
        code = _supervise(logs, timeout, grace, limit, command, status)
    except BaseException as exc:
        if status["failure"] is None:
            status["failure"] = repr(exc)[:4096]
        else:
            status["close_errors"].append(repr(exc)[:4096])
    if status["close_errors"] or status["publication_errors"]:
        code = 125
    status["returncode"] = code
    try:
        fd = os.open(
            logs / "supervisor.status.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        try:
            # Preserve write AND close errors, not context-manager replacement.
            stream = os.fdopen(fd, "w", closefd=False)
            try:
                json.dump(status, stream)
            except BaseException as exc:
                status["publication_errors"].append(repr(exc)[:4096])
                code = status["returncode"] = 125
            finally:
                try:
                    stream.close()
                except BaseException as exc:
                    status["publication_errors"].append(repr(exc)[:4096])
                    code = status["returncode"] = 125
        finally:
            os.close(fd)
    except BaseException as exc:
        status["publication_errors"].append(repr(exc)[:4096])
        code = status["returncode"] = 125
    if fallback is not None:
        try:
            data = _fallback_summary(status)
            while data:
                written = os.write(fallback, data)
                if written <= 0:
                    raise OSError("fallback short write")
                data = data[written:]
        except OSError:
            # Even if every persistence path fails, caller receives nonzero
            # plus the known private directory; never claim successful capture.
            code = 125
        finally:
            try:
                os.close(fallback)
            except OSError:
                code = 125
    return code


def _fallback_summary(status):
    """Keep the primary first; bound fields BEFORE encoding valid JSON."""
    width = 1024
    while True:
        truncated = False

        def clip(value, size):
            nonlocal truncated
            if value is None:
                return None
            if len(value) > size:
                truncated = True
                return value[:size] + " [truncated]"
            return value

        summary = {
            "failure": clip(status["failure"], width),
            "cleanup": clip(status["cleanup"], width // 4),
            "family_cleanup": status["family_cleanup"],
            "returncode": status["returncode"],
            "truncated": {
                name: True
                for name in ("stdout", "stderr")
                if status["truncated"].get(name)
            },
        }
        for name in ("close_errors", "publication_errors"):
            entries = status[name]
            truncated |= len(entries) > 3
            summary[name] = [clip(entry, width // 8) for entry in entries[:3]]
        summary["diagnostics_truncated"] = truncated
        data = json.dumps(summary, ensure_ascii=True).encode("utf-8")
        if len(data) <= 16384:
            return data
        width //= 2


def _supervise(logs, timeout, grace, limit, command, status):
    """External CLI only: all process-wide changes stay outside unittest."""
    cancelled = []

    def defer(signum, frame):
        if not cancelled:
            cancelled.append(signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGALRM):
        signal.signal(sig, defer)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot enable external subreaper")
    process = None
    code = 125

    def close_stream(stream, fd):
        try:
            stream.close()
        except BaseException as exc:
            status["close_errors"].append(repr(exc)[:4096])
        finally:
            # Output streams use closefd=False: own the fd independently of
            # buffered flush and its error path.
            try:
                os.close(fd)
            except OSError as exc:
                status["close_errors"].append(repr(exc)[:4096])

    def close_pipe(stream):
        fd = stream.fileno()
        try:
            stream.close()
        except BaseException as exc:
            status["close_errors"].append(repr(exc)[:4096])
            if not stream.closed:
                try:
                    os.close(fd)
                except OSError as secondary:
                    status["close_errors"].append(repr(secondary)[:4096])

    def close_selector(selector):
        try:
            selector.close()
        except BaseException as exc:
            status["close_errors"].append(repr(exc)[:4096])
            try:
                fd = selector.fileno()
            except (ValueError, AttributeError):
                pass  # already closed
            else:
                try:
                    os.close(fd)
                except OSError as secondary:
                    status["close_errors"].append(repr(secondary)[:4096])

    with ExitStack() as stack:
        selector = selectors.DefaultSelector()
        stack.callback(close_selector, selector)
        outputs = {}
        sizes = {}
        for name in ("stdout", "stderr"):
            fd = os.open(
                logs / ("driver." + name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            try:
                outputs[name] = os.fdopen(fd, "wb", closefd=False)
            except BaseException:
                os.close(fd)
                raise
            stack.callback(close_stream, outputs[name], fd)
            sizes[name] = 0

        def pump():
            for key, _ in selector.select(0.01):
                data = os.read(key.fd, 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                keep = data[: max(0, limit - sizes[name])]
                outputs[name].write(keep)
                sizes[name] += len(keep)
                if len(keep) < len(data):
                    status["truncated"][name] = True

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            for stream in (process.stdout, process.stderr):
                stack.callback(close_pipe, stream)
            for name in outputs:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            deadline = time.monotonic() + timeout
            while True:
                result = observation(process.pid)
                if result is not None:
                    code = (
                        result.si_status
                        if result.si_code == os.CLD_EXITED
                        else 128 + result.si_status
                    )
                    break
                if cancelled:
                    code = 128 + cancelled[0]
                    raise InterruptedError("supervisor cancellation")
                if time.monotonic() >= deadline:
                    code = 124
                    raise TimeoutError("driver deadline exceeded")
                pump()
        except BaseException as exc:
            status["failure"] = repr(exc)[:4096]
        finally:
            if process is not None:
                # Capture failure must not prevent family cleanup. A failed pump
                # is remembered and replaced with bounded sleep for escalation.
                pump_failed = []

                def cleanup_pump():
                    if not pump_failed:
                        try:
                            pump()
                            return
                        except Exception as exc:
                            pump_failed.append(repr(exc))
                    time.sleep(0.01)

                try:
                    cleanup(process.pid, grace, cleanup_pump)
                    status["family_cleanup"] = "verified"
                    process.returncode = code
                    # Bounded tail capture: EOF need not arrive from escaped FDs.
                    end = time.monotonic() + 0.2
                    while selector.get_map() and time.monotonic() < end:
                        cleanup_pump()
                    if pump_failed:
                        raise RuntimeError("capture failure: " + repr(pump_failed))
                except BaseException as exc:
                    status["cleanup"] = repr(exc)[:4096]
                    code = 125
    if cancelled and status["failure"] is None:
        status["failure"] = f"InterruptedError: supervisor signal {cancelled[0]}"
        if status["cleanup"] is None:
            code = 128 + cancelled[0]
    return code


if __name__ == "__main__":
    sys.exit(
        supervise(
            Path(sys.argv[1]),
            float(sys.argv[2]),
            float(sys.argv[3]),
            int(sys.argv[4]),
            sys.argv[5:],
        )
    )
