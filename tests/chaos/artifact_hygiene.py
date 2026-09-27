"""Keep test temp directories only when they explain a failure.

A test (or test class) registers the temporary directories it creates. After
unittest has recorded the outcome, directories of passing tests are removed.
They are kept, and their paths printed, when the test failed or errored, when
the class never ran a test (for example setUpClass failed), when no result
object is available, when ``NYARLATHACK_KEEP_ARTIFACTS=1``, or on GitHub
Actions (whose runner is discarded after uploading diagnostics).

Removal never follows symlinks and never touches a path the test did not
register. Nothing here changes what a test asserts or where it writes.
"""

import os
from pathlib import Path
import shutil
import stat
import sys
import unittest

KEEP_ENV = "NYARLATHACK_KEEP_ARTIFACTS"


def keep_requested(environ=None):
    """True for NYARLATHACK_KEEP_ARTIFACTS=1, and always on GitHub Actions.

    Hosted runners are discarded after the job, and the Quality workflow
    uploads fixture diagnostics after a passing suite too, so CI keeps them.
    """
    env = os.environ if environ is None else environ
    return env.get(KEEP_ENV) == "1" or env.get("GITHUB_ACTIONS") == "true"


def _owner_writable(function, path, _exc):
    """rmtree error hook: make an owned, non-symlink parent writable, retry once."""
    parent = os.path.dirname(path)
    for target in (parent, path):
        try:
            st = os.lstat(target)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid():
            os.chmod(target, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)
    function(path)


def remove_tree(path):
    """Delete path without following symlinks. Returns True when it is gone."""
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_dir():
            path.unlink(missing_ok=True)
        elif sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_owner_writable)
        else:  # pragma: no cover - Python 3.11 CI lint image only
            shutil.rmtree(path, onerror=lambda f, p, e: _owner_writable(f, p, e))
    except OSError as exc:
        print(f"ARTIFACTS_CLEANUP_FAILED={path}: {exc}", file=sys.stderr, flush=True)
    return not os.path.lexists(path)


def release(paths, failed, environ=None):
    """Remove registered paths after success; otherwise report them as kept."""
    keep = failed or keep_requested(environ)
    for path in paths:
        if keep:
            if os.path.lexists(path):
                print(f"ARTIFACTS_RETAINED={path}", file=sys.stderr, flush=True)
        else:
            remove_tree(path)


def _problems(result):
    return sum(
        len(getattr(result, name, ()))
        for name in ("failures", "errors", "unexpectedSuccesses")
    )


class _ClassState:
    def __init__(self):
        self.paths = []
        self.passed = 0
        self.failed = False


_CLASS_STATE = {}


_RUNNING = []


def track(test, path):
    """Register path with test if it supports hygiene; always return path.

    Helpers shared with plain TestCase classes call this, so the helper keeps
    working (and simply retains the path) outside RetainOnFailure.
    """
    register = getattr(test, "track_artifacts", None)
    return register(path) if register is not None else path


def track_running(path):
    """Register path with the RetainOnFailure test currently running, if any."""
    return _RUNNING[-1].track_artifacts(path) if _RUNNING else path


class RetainOnFailure(unittest.TestCase):
    """TestCase base that removes registered temp dirs only for passing tests."""

    def track_artifacts(self, path):
        """Register a per-test path; returns it unchanged for inline use."""
        self.__dict__.setdefault("_tracked_artifacts", []).append(Path(path))
        return path

    @classmethod
    def track_class_artifacts(cls, path):
        """Register a path shared by the class (normally from setUpClass)."""
        state = _CLASS_STATE.get(cls)
        if state is None:
            state = _CLASS_STATE[cls] = _ClassState()
            cls.addClassCleanup(cls._release_class_artifacts)
        state.paths.append(Path(path))
        return path

    @classmethod
    def _release_class_artifacts(cls):
        state = _CLASS_STATE.pop(cls, None)
        if state is not None:
            release(state.paths, state.failed or state.passed == 0)

    def run(self, result=None):
        if result is None:
            # No shared result to inspect: keep everything (conservative).
            outcome = super().run(result)
            self.__dict__.pop("_tracked_artifacts", None)
            state = _CLASS_STATE.get(type(self))
            if state is not None:
                state.failed = True
            return outcome
        before = _problems(result)
        _RUNNING.append(self)
        try:
            return super().run(result)
        finally:
            _RUNNING.remove(self)
            failed = _problems(result) > before
            state = _CLASS_STATE.get(type(self))
            if state is not None:
                if failed:
                    state.failed = True
                else:
                    state.passed += 1
            release(self.__dict__.pop("_tracked_artifacts", []), failed)
