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
# C (broad next-use): next_use_program_v 3 answers every use of its family
# until it delivers BROAD_USES effects; its telegraph says so ("For a while").
_TELEGRAPH_BROAD = {"W": "next-use-v3-W", "F": "next-use-v3-F"}
BROAD_USES = 2
# Ring (new runs only): a W program is next_use_program_v 4, a broad program
# whose "w_effect" is "ring"; the effect pins its telegraph. F programs are
# written exactly as under C.
_TELEGRAPH_RING = "next-use-v4-Wr"
W_EFFECT_RING = "ring"


def engine_run_hex(directory):
    """Same 64-hex run identity chaos_engine next_use_bind_owned emits."""
    st = os.stat(directory, follow_symlinks=False)
    dev = st.st_dev & 0xFFFFFFFFFFFFFFFF
    ino = st.st_ino & 0xFFFFFFFFFFFFFFFF
    return f"{dev:016x}{ino:016x}{dev:016x}{ino:016x}"


def _hex64(value):
    return (
        type(value) is str
        and len(value) == 64
        and set(value) <= set("0123456789abcdef")
    )


def _int_range(value, lo, hi):
    return type(value) is int and lo <= value <= hi


def program_lifetime(ordinal, repair=True):
    """Native moves a program lives: 100, or 300 for a repaired program 2-3.

    The envelope's ttl also selects the engine's rules for programs 2-3:
    300 checks the companion only at the whistle (recurrence repair); 100 keeps
    the pre-repair admission check, for runs recorded before the repair.
    """
    if type(ordinal) is not int or not 1 <= ordinal <= 3 or type(repair) is not bool:
        raise ValueError("next-use program ordinal")
    return 300 if repair and ordinal > 1 else 100


def envelope_from_selection(
    selected, host, ordinal=1, repair=True, broad=False, ring=False
):
    """Map one trusted row plus host scheduling into the C envelope schema.

    broad (C, new runs only) writes next_use_program_v 3 with "uses"; it needs
    the recurrence repair rules, which it builds on. ring (new runs only)
    builds on broad: a W effect row becomes a v4 ring program.
    """
    if type(broad) is not bool or (broad and not repair):
        raise ValueError("broad next-use needs the recurrence repair rules")
    if type(ring) is not bool or (ring and not broad):
        raise ValueError("ring needs the broad next-use rules")
    ttl = program_lifetime(ordinal, repair)
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
    family = row["family"]
    # Q1: in a ring run every W program is a ring program (a quiet row stays
    # quiet in its source; its telegraph and rules are ring's).
    ring_program = ring and family == "W"
    composed = compose(row, ring=ring_program)
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
        "next_use_program_v": 4 if ring_program else 3 if broad else 2,
        "operations": [family],
        "origin_refs": [origin],
        "source": composed["source"],
        "source_sha256": composed["source_sha256"],
        "telegraph": _TELEGRAPH_RING
        if ring_program
        else (_TELEGRAPH_BROAD if broad else _TELEGRAPH)[family],
        "ttl": ttl,
        "variant": host["variant"],
    }
    if broad:
        envelope["uses"] = BROAD_USES
    if ring_program:
        envelope["w_effect"] = W_EFFECT_RING
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


def envelope_name(ordinal=1):
    if type(ordinal) is not int or not 1 <= ordinal <= 3:
        raise ValueError("next-use program ordinal")
    return _ENVELOPE_NAME if ordinal == 1 else f"next_use-envelope.{ordinal}.json"


def publish_envelope(
    directory,
    selected,
    host,
    box=None,
    ordinal=1,
    repair=True,
    broad=False,
    ring=False,
):
    """Write one complete envelope artifact. Never admits."""
    name = envelope_name(ordinal)
    envelope, encoded = envelope_from_selection(
        selected, host, ordinal, repair, broad, ring
    )

    def write(held):
        target = held.path / name
        if os.path.lexists(target):
            raise ValueError(
                "a next-use envelope already exists; use a fresh game directory"
            )
        fd, tmp = tempfile.mkstemp(prefix=".next-use-envelope-", dir=held.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
            os.link(tmp, target)
        finally:
            os.unlink(tmp)
        dfd = os.open(held.path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        mode = os.stat(target, follow_symlinks=False).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError("regular next-use envelope required")
        os.chmod(target, 0o600)

    if box is None:
        with Mailbox(directory) as held:
            write(held)
    else:
        write(box)
    return {
        "status": "envelope_published_not_admitted",
        "path": name,
        "id": envelope["id"],
        "source_sha256": envelope["source_sha256"],
        "bytes": len(encoded),
    }
