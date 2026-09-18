"""Install a next-use source candidate; only the game can admit it. NGPL."""

import os
import stat
import tempfile

from .director import Mailbox
from .next_use_compose import compose


def install(directory, selected):
    composed = compose(selected)
    raw = composed["source"].encode("ascii")
    with Mailbox(directory) as box:
        target = box.path / "next_use.lua"
        if os.path.lexists(target) or os.path.lexists(box.path / "next_use-used.lua"):
            raise ValueError(
                "a next-use candidate already exists; use a fresh game directory"
            )
        fd, tmp = tempfile.mkstemp(prefix=".next-use-", dir=box.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.link(tmp, target)
        finally:
            os.unlink(tmp)
        dfd = os.open(box.path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        mode = os.stat(target, follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError("regular next-use source required")
        os.chmod(target, 0o600)
    return {
        "status": "candidate_installed_not_admitted",
        "family": composed["family"],
        "op": composed["op"],
        "source_sha256": composed["source_sha256"],
    }
