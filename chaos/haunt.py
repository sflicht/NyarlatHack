"""Install a source candidate; only the game can validate and admit it. NGPL."""

import hashlib
import os
import stat
import tempfile
from .director import Mailbox


def install(source, directory):
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("regular source file required")
        raw = f.read(4097)
    if not 0 < len(raw) <= 4096 or b"\0" in raw:
        raise ValueError("source bounds violated")
    with Mailbox(directory) as box:
        target = box.path / "haunting.lua"
        if os.path.lexists(target) or os.path.lexists(box.path / "haunting-used.lua"):
            raise ValueError("a candidate already exists; use a fresh game directory")
        fd, tmp = tempfile.mkstemp(prefix=".haunt-", dir=box.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            # Exclusive atomic publication. The transient second link fails closed in C.
            os.link(tmp, target)
        finally:
            os.unlink(tmp)
        dfd = os.open(box.path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    return {
        "status": "candidate_installed_not_admitted",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
    }
