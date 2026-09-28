"""Install a source candidate; only the game can validate and admit it. NGPL."""

import hashlib
import os
from pathlib import Path
import stat
import tempfile
from .director import Mailbox

CANDIDATE = "haunting.lua"
USED = "haunting-used.lua"
DEFAULT_PACK = Path(__file__).resolve().parent / "packs" / "footsteps.lua"


def read_source(source):
    """Bounded, regular, NUL-free source bytes (the game re-checks all of it)."""
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("regular source file required")
        raw = f.read(4097)
    if not 0 < len(raw) <= 4096 or b"\0" in raw:
        raise ValueError("source bounds violated")
    return raw


def publish(path, raw):
    """Exclusive atomic publication into a mailbox directory the caller locked."""
    path = Path(path)
    target = path / CANDIDATE
    if os.path.lexists(target) or os.path.lexists(path / USED):
        raise ValueError("a candidate already exists; use a fresh game directory")
    fd, tmp = tempfile.mkstemp(prefix=".haunt-", dir=path)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        # Exclusive atomic publication. The transient second link fails closed in C.
        os.link(tmp, target)
    finally:
        os.unlink(tmp)
    dfd = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return {
        "status": "candidate_installed_not_admitted",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def verify(path, raw):
    """Restore: the installed candidate must be these exact bytes; no repair."""
    path = Path(path)
    if read_source(path / CANDIDATE) != raw:
        raise ValueError("installed haunting candidate differs from the pack")
    return {
        "status": "candidate_verified_not_admitted",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }


def install(source, directory):
    raw = read_source(source)
    with Mailbox(directory) as box:
        return publish(box.path, raw)
