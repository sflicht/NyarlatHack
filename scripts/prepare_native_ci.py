#!/usr/bin/env python3
"""Build selected disposable CI checkout and private historical comparison.

No network, model calls, retries, receipt command replay or gameplay. The caller
selects a trusted clean full-history checkout and independent full revision.
Receipts measure this run; they are not hostile same-UID writer attestation.
"""

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

OLD_REVISION = "4610d90612e3c255b37786e385d86f981b016bc2"
BASELINE_REVISION = "fd7a91deb1dc33244e0f72a47d3a4ec584255852"
COMPILER = "cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0"
PKG_FLAGS = "-I/usr/include/lua5.4 -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=600 -llua5.4 -lncursesw -ltinfo"
PAIRS = {"dnethack": "src/dnethack", "nhdat": "dat/nhdat", "license": "dat/license"}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def stamp():
    return datetime.now(ZoneInfo("America/New_York")).isoformat()


def digest(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, f"unsafe file: {path}")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    with path.open("w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")


def environment():
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(Path.home()),
        "LANG": "C.UTF-8",
        "TZ": "America/New_York",
        "PKG_CONFIG_LIBDIR": "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig",
    }


def output(root, env, argv):
    return subprocess.run(
        argv, cwd=root, env=env, capture_output=True, text=True, check=True, timeout=60
    ).stdout


def git(root, *args):
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    return output(root, env, ["/usr/bin/git", *args]).strip()


def check_tree(root, revision):
    require(git(root, "rev-parse", "HEAD") == revision, "revision mismatch")
    require(
        git(root, "rev-parse", "--is-shallow-repository") == "false",
        "full history required",
    )
    require(
        not git(root, "status", "--porcelain", "--untracked-files=no"),
        "dirty tracked tree",
    )
    require(
        all(
            item.startswith("H ")
            for item in git(root, "ls-files", "-v", "-z").split("\0")
            if item
        ),
        "unsupported index flags",
    )
    require(not os.path.lexists(root / "local.mk"), "local.mk override forbidden")


def protected_inputs(root):
    paths = [root / p for p in git(root, "ls-files", "-z").split("\0") if p]
    require(bool(paths), "empty tracked preservation set")
    return {str(p): digest(p) for p in paths}


def copy_tuple(source, destination, pairs, *, archive=False):
    destination.mkdir(mode=0o700)
    for name, pair in pairs.items():
        target = destination / name
        shutil.copyfile(source / name, target)
        target.chmod(0o444 if archive else (0o755 if name == "dnethack" else 0o644))
        require(digest(target) == pair["sha256"], f"tuple copy hash mismatch: {name}")


def _group_running(pgid):
    """Linux only: zombies cannot write, but a zombie leader may have live threads."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) != pgid:
                continue
            if fields[0] not in ("Z", "X"):
                return True
            for task in (entry / "task").iterdir():
                state = (task / "stat").read_text().rsplit(")", 1)[1].split()[0]
                if state not in ("Z", "X"):
                    return True
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False


def _stop_build_group(process):
    """Bound TERM/KILL waits; reap only our direct child, never grandchildren."""
    try:
        for sig, grace in ((signal.SIGTERM, 1.0), (signal.SIGKILL, 2.0)):
            # The unreaped leader pins this invocation's PGID until cleanup ends.
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            deadline = time.monotonic() + grace
            while _group_running(process.pid):
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
            else:
                return
        require(not _group_running(process.pid), "build process group still running")
    finally:
        # Even failed /proc inspection must not bypass escalation. The leader
        # is still unreaped here, so this cannot target a reused process group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def _run_build(argv, *, cwd, env, stdout, stderr, timeout):
    """Main-thread Linux supervisor; no containment of setsid/escaped daemons.

    Hold the leader waitable (WNOWAIT) to prevent PGID reuse during cleanup.
    Defer SIGINT/SIGTERM, including repeated signals, until group cleanup is done.
    A timeout/interruption never yields a CompletedProcess or successful receipt.
    """
    previous = {}
    interrupted = []

    def on_signal(signum, frame):
        if not interrupted:
            interrupted.append(
                KeyboardInterrupt()
                if signum == signal.SIGINT
                else SystemExit(128 + signum)
            )

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, on_signal)
        process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr, start_new_session=True
        )
        failure = None
        try:
            deadline = time.monotonic() + timeout
            while True:
                if interrupted:
                    raise interrupted[0]
                if os.waitid(
                    os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                ):
                    break
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(argv, timeout)
                time.sleep(0.02)
        except BaseException as exc:
            failure = exc
        try:
            _stop_build_group(process)
        except BaseException as exc:
            if failure is None:
                failure = exc
            else:
                failure.add_note(f"build group cleanup failed: {exc!r}")
            setattr(failure, "_build_cleanup_failed", True)
        if failure is not None:
            raise failure
        if interrupted:
            raise interrupted[0]
        return subprocess.CompletedProcess(argv, process.returncode)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def build_mode(root, receipts, revision, env, mode, *, historical=False):
    commands = []
    for target in ("clean", "install"):
        argv = [
            "/usr/bin/make",
            "-j2",
            target,
            f"CHAOS={mode}",
            "CC=/usr/bin/cc",
            "PKG_CONFIG=/usr/bin/pkg-config",
        ]
        log = receipts / f"{mode}-{target}.log"
        started = stamp()
        code = None
        primary_error = None
        try:
            with log.open("wb") as stream:
                try:
                    os.fchmod(stream.fileno(), 0o600)
                    result = _run_build(
                        argv,
                        cwd=root,
                        env=env,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        timeout=480,
                    )
                    code = result.returncode
                except BaseException as exc:
                    # Retain cleanup status before closing the log can fail.
                    primary_error = exc
        except BaseException as exc:
            if primary_error is None:
                primary_error = exc
            else:
                primary_error.add_note(f"build log finalization failed: {exc!r}")
        try:
            # null means no exit status was obtained (e.g. timeout), never success.
            commands.append(
                dict(
                    argv=argv,
                    log=str(log),
                    started_eastern=started,
                    finished_eastern=stamp(),
                    exit_code=code,
                )
            )
            save(receipts / f"{mode}-commands.json", commands)
        except BaseException as exc:
            if primary_error is None:
                raise
            primary_error.add_note(f"build command receipt failed: {exc!r}")
        if primary_error is not None:
            raise primary_error
        require(code == 0, f"build failed ({code}): {log}")
    require(
        (root / ".chaos-build").read_text().strip() == str(mode), "build mode mismatch"
    )
    check_tree(root, revision)
    pairs = {}
    for name, relative in PAIRS.items():
        source, installed = root / relative, root / "dnethackdir" / name
        value = digest(source)
        require(
            source.stat().st_size > 0 and digest(installed) == value,
            f"installed tuple mismatch: {name}",
        )
        pairs[name] = {"sha256": value, "size": source.stat().st_size}
    symbols = output(
        root, env, ["/usr/bin/nm", "-S", str(root / "dnethackdir/dnethack")]
    )
    selected = [
        line
        for line in symbols.splitlines()
        if line.split()
        and line.split()[-1]
        in {
            "inert_bones_curios",
            "chaos_curio_init",
            "chaos_curio_apply",
            "savebones",
            "restobjchn",
        }
    ]
    if historical or mode == 0:
        require("chaos_curio_" not in symbols, "unexpected curio symbols")
    else:
        require(
            any(line.split()[-1] == "inert_bones_curios" for line in selected),
            "missing curio bones symbol",
        )
    (receipts / f"{mode}-elf-notes.txt").write_text(
        output(
            root, env, ["/usr/bin/readelf", "-n", str(root / "dnethackdir/dnethack")]
        )
    )
    headers = {
        str(p.relative_to(root)): digest(p) for p in (root / "include").glob("*.h")
    }
    require("include/date.h" in headers, "missing generated include/date.h")
    # Preserve this mode before the next clean; bind raw bytes to the existing hash.
    date_bytes = (root / "include/date.h").read_bytes()
    capture = receipts / f"{mode}-date.h"
    with os.fdopen(
        os.open(capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as stream:
        stream.write(date_bytes)
    require(
        digest(capture) == headers["include/date.h"], "date.h capture hash mismatch"
    )
    objects = {
        str(p.relative_to(root)): digest(p)
        for d in ("src", "util", "sys", "win")
        for p in (root / d).rglob("*.o")
    }
    require(headers and objects, "missing build inputs")
    manifest = dict(
        mode=mode,
        revision=revision,
        pairs=pairs,
        symbols=selected,
        generated_headers=headers,
        objects=objects,
        commands=commands,
        finished_eastern=stamp(),
        acceptance="Build and binary identity only; no gameplay or tests",
    )
    save(receipts / f"{mode}-manifest.json", manifest)
    return pairs


def build(root, receipts, revision, env, modes, out, *, historical=False):
    receipts.mkdir(mode=0o700)
    check_tree(root, revision)
    protected = protected_inputs(root)
    compiler = output(root, env, ["/usr/bin/cc", "--version"])
    pkg_flags = output(
        root, env, ["/usr/bin/pkg-config", "--cflags", "--libs", "lua5.4", "ncursesw"]
    )
    save(
        receipts / "preflight.json",
        dict(
            revision=revision,
            tree=git(root, "rev-parse", "HEAD^{tree}"),
            environment=env,
            started_eastern=stamp(),
            compiler=compiler,
            pkg_flags=pkg_flags,
            protected=protected,
            disk_free=shutil.disk_usage(out).free,
        ),
    )
    finished = []
    primary_error = None
    try:
        require(
            compiler.splitlines() and compiler.splitlines()[0] == COMPILER,
            "unsupported actual compiler; existing verifier contract unchanged",
        )
        require(
            pkg_flags.split() == PKG_FLAGS.split(),
            "unsupported actual pkg-config flags",
        )
        for mode in modes:
            pairs = build_mode(
                root, receipts, revision, env, mode, historical=historical
            )
            if historical:
                copy_tuple(root / "dnethackdir", out / "precurio", pairs)
            elif mode == 0:
                copy_tuple(
                    root / "dnethackdir", out / "off-archive", pairs, archive=True
                )
                copy_tuple(out / "off-archive", out / "stock", pairs)
            finished.append(mode)
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            if getattr(primary_error, "_build_cleanup_failed", False):
                raise RuntimeError(
                    "build cleanup unverified; final input measurement skipped"
                )
            after = protected_inputs(root)
            save(
                receipts / "completion.json",
                dict(
                    finished_modes=finished,
                    protected_unchanged=after == protected,
                    protected_after=after,
                    finished_eastern=stamp(),
                    disk_free=shutil.disk_usage(out).free,
                ),
            )
            require(after == protected, "tracked inputs changed during build")
        except Exception as exc:
            # Missing/unsafe tracked inputs are evidence, not a replacement for
            # the timeout, interruption or command failure that brought us here.
            try:
                save(
                    receipts / "preservation-failure.json",
                    dict(
                        primary_error=repr(primary_error)
                        if primary_error is not None
                        else None,
                        preservation_error=f"{type(exc).__name__}: {exc}",
                        finished_eastern=stamp(),
                    ),
                )
            except Exception as diagnostic_error:
                exc.add_note(
                    f"cannot save preservation diagnostic: {diagnostic_error!r}"
                )
            if primary_error is None:
                raise
            primary_error.add_note(f"tracked-input preservation failed: {exc!r}")


def verify_selection(root, receipts, revision):
    # Import only the selected checkout's checked verifier; no receipt chooses code.
    sys.path.insert(0, str(root / "tests/chaos"))
    try:
        from native_fixture_selection import prepare as select

        return select(
            root,
            {
                "NYARLATHACK_NATIVE_FIXTURE_MODE": "source-build",
                "NYARLATHACK_NATIVE_BUILD_RECEIPT": str(receipts),
                "NYARLATHACK_NATIVE_EXPECTED_REVISION": revision,
            },
        ).record()
    finally:
        sys.path.pop(0)


def prepare(root, out, revision):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("expected revision must be full lowercase 40hex")
    root, out = Path(root), Path(out)
    for p in (root, out):
        if (
            not p.is_absolute()
            or p != p.resolve()
            or any(c in str(p) for c in "\r\n\0")
        ):
            raise ValueError("paths must be canonical absolute paths without symlinks")
    if out.is_relative_to(root) or root.is_relative_to(out):
        raise ValueError("checkout and output must be disjoint")
    if os.path.lexists(out):
        raise FileExistsError(out)
    check_tree(root, revision)
    for fixed in (OLD_REVISION, BASELINE_REVISION):
        require(
            git(root, "rev-parse", fixed + "^{commit}") == fixed,
            f"reviewed historical revision unavailable: {fixed}",
        )
    old_umask = os.umask(0o077)
    try:
        out.mkdir(mode=0o700)
        for name in ("fixtures", "home"):
            (out / name).mkdir(mode=0o700)
        (out / "MAIL").touch(mode=0o600, exist_ok=False)
        env = environment()
        old = out / "old-checkout"
        # Local clone only: no hardlinks, shared object store, worktrees or fallback.
        clone = ["clone", "--no-hardlinks", "--no-checkout", "--", str(root), str(old)]
        clone_output = git(root, *clone)
        checkout_output = git(old, "checkout", "--detach", OLD_REVISION)
        save(
            out / "old-checkout.json",
            {
                "source": str(root),
                "revision": OLD_REVISION,
                "clone_argv": ["/usr/bin/git", *clone],
                "clone_stdout": clone_output,
                "checkout_stdout": checkout_output,
                "actual_revision": git(old, "rev-parse", "HEAD"),
            },
        )
        build(old, out / "old-on", OLD_REVISION, env, (1,), out, historical=True)
        build(root, out / "system-gcc13", revision, env, (0, 1), out)
        selection = verify_selection(root, out / "system-gcc13", revision)
        save(out / "source-selection.json", selection)
        save(
            out / "preparation.json",
            {
                "revision": revision,
                "old_revision": OLD_REVISION,
                "stock_dir": str(out / "stock"),
                "precurio_dir": str(out / "precurio"),
                "receipt_dir": str(out / "system-gcc13"),
                "scope": "Build preparation only; suite and native calibration not yet run",
            },
        )
    finally:
        os.umask(old_umask)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-revision", required=True)
    args = parser.parse_args()
    prepare(args.root, args.output_dir, args.expected_revision)


if __name__ == "__main__":
    main()
