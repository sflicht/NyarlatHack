"""Publish one immutable next-use envelope. Not admission. NGPL."""

import hashlib
import json
import os
import stat
import tempfile

from .director import Mailbox
from .next_use_compose import compose, validate_next_use_row

_ENVELOPE_NAME = "next_use-envelope.json"
_SEQ_MAX = 2147483647
_ENGINE_FACTS = {"W": "ordinary_whistle", "F": "water_refreshed"}
_TELEGRAPH = {"W": "next-use-v2-W", "F": "next-use-v2-F"}


def _hex64(value):
    return (
        type(value) is str
        and len(value) == 64
        and set(value) <= set("0123456789abcdef")
    )


def _int_range(value, lo, hi):
    return type(value) is int and lo <= value <= hi


def envelope_from_selection(selected, host):
    """Map one trusted row plus host scheduling into the C envelope schema."""
    if type(host) is not dict:
        raise ValueError("host scheduling fields required")
    required = (
        "at",
        "id",
        "level_dlevel",
        "level_dnum",
        "move",
        "run",
        "variant",
    )
    if set(host) != set(required):
        raise ValueError("host scheduling field set")
    if not (
        _int_range(host["at"], 0, _SEQ_MAX)
        and _int_range(host["id"], 1, _SEQ_MAX)
        and _int_range(host["level_dlevel"], 0, 255)
        and _int_range(host["level_dnum"], 0, 255)
        and _int_range(host["move"], 0, _SEQ_MAX)
        and _int_range(host["variant"], 0, 2)
        and _hex64(host["run"])
    ):
        raise ValueError("host scheduling provenance")
    row = validate_next_use_row(selected)
    composed = compose(row)
    family = row["family"]
    origin = {
        "end_seq": row["origin"]["end_seq"],
        "fact": _ENGINE_FACTS[family],
        "family": family,
        "level_dlevel": host["level_dlevel"],
        "level_dnum": host["level_dnum"],
        "move": host["move"],
        "notice_seq": row["origin"]["notice_seq"],
        "root": row["origin"]["root_seq"],
        "run": host["run"],
    }
    envelope = {
        "at": host["at"],
        "cost": 1,
        "id": host["id"],
        "next_use_program_v": 2,
        "operations": [family],
        "origin_refs": [origin],
        "source": composed["source"],
        "source_sha256": composed["source_sha256"],
        "telegraph": _TELEGRAPH[family],
        "ttl": 100,
        "variant": host["variant"],
    }
    encoded = json.dumps(
        envelope,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if not 0 < len(encoded) <= 8192:
        raise ValueError("envelope size")
    if (
        hashlib.sha256(composed["source"].encode("ascii")).hexdigest()
        != composed["source_sha256"]
    ):
        raise ValueError("source digest")
    return envelope, encoded


def publish_envelope(directory, selected, host):
    """Write one complete envelope artifact. Never admits."""
    envelope, encoded = envelope_from_selection(selected, host)
    with Mailbox(directory) as box:
        target = box.path / _ENVELOPE_NAME
        if os.path.lexists(target):
            raise ValueError(
                "a next-use envelope already exists; use a fresh game directory"
            )
        fd, tmp = tempfile.mkstemp(prefix=".next-use-envelope-", dir=box.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encoded)
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
            raise ValueError("regular next-use envelope required")
        os.chmod(target, 0o600)
    return {
        "status": "envelope_published_not_admitted",
        "path": _ENVELOPE_NAME,
        "id": envelope["id"],
        "source_sha256": envelope["source_sha256"],
        "bytes": len(encoded),
    }
