"""Offline, exact-byte candidate evidence and pre-game installation. NGPL.

API (all paths are HOST supplied, never taken from an envelope):
* store_candidate(bundle_root, raw_response: str) -> frozen Candidate.
  Existing private bundle_root is required. Exclusively creates its SHA-256
  source identity subdirectory with raw-response.json (exact UTF-8 response),
  source.lua (exact decoded bytes), continuity-note.txt (exact UTF-8 note), and
  manifest.json (version 1, host-computed bindings). Reparse then read back.
  Reject even identical existing bundles: use read_candidate explicitly instead.
* read_candidate(bundle_root, candidate_id) -> frozen Candidate. Require a full
  lowercase SHA-256 identity, exact file set, strict manifest and reparsed raw
  envelope matching every source/note byte and digest. No class-instance bypass.
* install_saved_source(run_directory, *, source_file=None, bundle_root=None,
  candidate_id=None, mode="fresh") -> installation receipt dict read from disk.
  Supply EITHER a private source_file OR bundle_root + candidate_id. The former
  is opaque 1..4096 bytes without NUL; it need not be UTF-8 or valid Lua. The
  latter is fully read/reparsed again, not a trusted caller-constructed object.
  Fresh mode exclusively publishes curio.lua then curio-install.json. Existing
  source, used source, receipt or our crash temporaries always conflict.
  Verify mode requires existing source, receipt and lock, compares optional
  curio-used.lua exactly, and performs NO creation, writes, fsync or cleanup.
  Verification observes evidence, NOT durability recovery or native acceptance.

Private resource directories must be owned, mode 0700, and nonsymlink (including
path ancestors, whose permissions need not be private). All files are owned,
regular, mode 0600, single-link, opened NONBLOCK/NOFOLLOW via directory FDs.
Reads enforce FD metadata/size caps before reading, cap even racing growth, and
check metadata and directory-entry identity afterwards. Filesystem/validation
failures raise OSError/ValueError; no success on sync/readback failure.

Publication is deliberately fail-closed, not an all-or-nothing transaction:
reserve the final bundle directory with exclusive mkdir and fsync its parent;
write/fsync private temporary files, link each fixed target exclusively, remove
only our temporary link, fsync inode then directory. Manifest/receipt is last.
Partial/published evidence is NEVER erased, repaired, overwritten or retried.
A crash can leave incomplete directories, transient two-link files or temporary
names; explicit readback rejects those. Even complete evidence after a failed
final fsync is ambiguous: fresh retry rejects; read/verify cannot certify the
failed durability step. Operator/recovery policy belongs to a later layer.

Installation takes the SAME nonblocking .director.lock flock as Mailbox, using
an anchored dirfd rather than its path-based implementation. This coordinates
sidecars only: caller MUST install before starting the game. It cannot stop an
already-running engine. curio-used.lua is never modified; its presence proves
neither admission nor placement. Native validation, live authorship evidence,
continuity journals, rollback reconciliation and inference are outside this API.
Private owned directories plus cooperating writers are the trust boundary, not
protection against malicious same-UID processes or hostile filesystem servers.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

from .curio import MAX_NOTE_BYTES, MAX_RESPONSE_BYTES, MAX_SOURCE_BYTES, parse_envelope
from .protocol import strict_json


_JSON_CAP = 1024
_ID = re.compile(r"[0-9a-f]{64}")
_BUNDLE_FILES = {
    "raw-response.json",
    "source.lua",
    "continuity-note.txt",
    "manifest.json",
}
_INSTALL_FILES = ("curio.lua", "curio-used.lua", "curio-install.json")
_TEMP_PREFIX = ".curio-"
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True)
class Candidate:
    """Verified transport evidence only, not native validation or authorship."""

    candidate_id: str
    raw_response: str
    lua_source: bytes
    continuity_note: str


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise ValueError("candidate_id must be 64 lowercase SHA-256 hex digits")
    return value


def _private(s, *, directory=False):
    kind, mode = (stat.S_ISDIR, 0o700) if directory else (stat.S_ISREG, 0o600)
    if (
        not kind(s.st_mode)
        or s.st_uid != os.getuid()
        or stat.S_IMODE(s.st_mode) != mode
        or (not directory and s.st_nlink != 1)
    ):
        raise ValueError("resource must be owned, private, nonsymlink and single-link")


@contextmanager
def _directory(path):
    # Walk rather than resolve(): resolving would silently accept symlinks.
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("parent traversal is not allowed")
    fd = os.open(path.anchor, _DIR_FLAGS)
    try:
        for part in path.parts[1:]:
            child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child
        _private(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


@contextmanager
def _bundle_directory(parent, identity):
    fd = os.open(identity, _DIR_FLAGS, dir_fd=parent)
    try:
        _private(os.fstat(fd), directory=True)
        yield fd
        _same_entry(parent, identity, os.fstat(fd))
    finally:
        os.close(fd)


def _same_entry(directory, name, snapshot):
    current = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (snapshot.st_dev, snapshot.st_ino):
        raise ValueError("resource replaced while open")


def _open_file(directory, name, flags=os.O_RDONLY):
    # Equivalent security checks to director.secure_open, anchored to a dirfd.
    fd = os.open(
        name,
        flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        0o600,
        dir_fd=directory,
    )
    try:
        _private(os.fstat(fd))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _snapshot(s):
    return (
        s.st_dev,
        s.st_ino,
        s.st_mode,
        s.st_uid,
        s.st_nlink,
        s.st_size,
        s.st_mtime_ns,
        s.st_ctime_ns,
    )


def _read(directory, name, cap):
    fd = _open_file(directory, name)
    try:
        before = os.fstat(fd)
        if not 0 <= before.st_size <= cap:
            raise ValueError("resource exceeds byte cap")
        raw = bytearray()
        while len(raw) <= cap:
            chunk = os.read(fd, cap + 1 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
        if len(raw) != before.st_size or _snapshot(os.fstat(fd)) != _snapshot(before):
            raise ValueError("resource changed or exceeded byte cap during read")
        _same_entry(directory, name, before)
        return bytes(raw)
    finally:
        os.close(fd)


def _exists(directory, name):
    try:
        os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _check_names(directory, *, bundle=False):
    # Bound scanning as well as file reads, and never forgive crash leftovers.
    names = set()
    with os.scandir(directory) as entries:
        for index, entry in enumerate(entries):
            if index >= (4 if bundle else 4096):
                raise ValueError("directory entry cap exceeded")
            if entry.name.startswith(_TEMP_PREFIX):
                raise ValueError(
                    "incomplete publication; manual reconciliation required"
                )
            if bundle:
                names.add(entry.name)
    if bundle and names != _BUNDLE_FILES:
        raise ValueError("missing, partial or conflicting candidate evidence")


def _json(raw, expected):
    # Decode explicitly: do not let json.loads auto-detect UTF-16/32 on bytes.
    obj = strict_json(raw.decode("utf-8"), _JSON_CAP)
    if obj.keys() != expected.keys() or any(
        type(obj[key]) is not type(value) or obj[key] != value
        for key, value in expected.items()
    ):
        raise ValueError("invalid schema or conflicting evidence binding")
    return obj


def _encode(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest(envelope):
    source_hash = _digest(envelope.lua_source)
    return {
        "version": 1,
        "provenance": "supplied_raw_envelope",
        "candidate_id": source_hash,
        "source_sha256": source_hash,
        "raw_response_sha256": _digest(envelope.raw_response.encode("utf-8")),
        "note_sha256": _digest(envelope.continuity_note.encode("utf-8")),
    }


def _publish(directory, name, raw):
    """Exclusive single-file publication; never unlink a final target on error."""
    temporary = _TEMP_PREFIX + uuid.uuid4().hex
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory,
    )
    has_temp = True
    try:
        os.fchmod(fd, 0o600)  # Safe only for this newly created exclusive inode.
        _private(os.fstat(fd))
        view = memoryview(raw)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise OSError("zero-length evidence write")
            view = view[n:]
        os.fsync(fd)
        _same_entry(directory, temporary, os.fstat(fd))
        os.link(
            temporary,
            name,
            src_dir_fd=directory,
            dst_dir_fd=directory,
            follow_symlinks=False,
        )
        # Engine requires nlink == 1; no receipt until this link is removed.
        os.unlink(temporary, dir_fd=directory)
        has_temp = False
        os.fsync(fd)  # Persist inode link-count metadata too.
        os.fsync(directory)
    finally:
        try:
            if has_temp:
                # Only the unpublished temporary NAME, never a final target.
                _same_entry(directory, temporary, os.fstat(fd))
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(fd)


def _read_candidate(directory, identity):
    _check_names(directory, bundle=True)
    raw = _read(directory, "raw-response.json", MAX_RESPONSE_BYTES)
    envelope = parse_envelope(raw.decode("utf-8"))
    expected = _manifest(envelope)
    if expected["candidate_id"] != identity:
        raise ValueError("source does not match candidate_id")
    if _read(directory, "source.lua", MAX_SOURCE_BYTES) != envelope.lua_source:
        raise ValueError("source does not match raw response")
    if _read(directory, "continuity-note.txt", MAX_NOTE_BYTES) != (
        envelope.continuity_note.encode("utf-8")
    ):
        raise ValueError("note does not match raw response")
    _json(_read(directory, "manifest.json", _JSON_CAP), expected)
    _check_names(directory, bundle=True)
    return Candidate(
        identity, envelope.raw_response, envelope.lua_source, envelope.continuity_note
    )


def read_candidate(bundle_root, candidate_id):
    """Reparse and verify an existing complete bundle; never repair or write."""
    identity = _identity(candidate_id)
    with _directory(bundle_root) as parent:
        with _bundle_directory(parent, identity) as directory:
            return _read_candidate(directory, identity)


def store_candidate(bundle_root, raw_response):
    """Reserve a fresh source-identity bundle; existing/partial bundles reject."""
    envelope = parse_envelope(raw_response)
    manifest = _manifest(envelope)
    identity = manifest["candidate_id"]
    with _directory(bundle_root) as parent:
        os.mkdir(identity, 0o700, dir_fd=parent)
        # The directory is now published: retain it even if this fsync fails.
        os.fsync(parent)
        with _bundle_directory(parent, identity) as directory:
            for name, raw in (
                ("raw-response.json", envelope.raw_response.encode("utf-8")),
                ("source.lua", envelope.lua_source),
                ("continuity-note.txt", envelope.continuity_note.encode("utf-8")),
                ("manifest.json", _encode(manifest)),
            ):
                _publish(directory, name, raw)
            return _read_candidate(directory, identity)


@contextmanager
def _writer_lock(directory, *, create):
    flags = os.O_RDWR | (os.O_CREAT if create else 0)
    fd = _open_file(directory, ".director.lock", flags)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("another director holds the run directory") from exc
        _same_entry(directory, ".director.lock", os.fstat(fd))
        yield
    finally:
        os.close(fd)


def _source(source_file, bundle_root, candidate_id):
    if source_file is not None and bundle_root is None and candidate_id is None:
        path = Path(source_file)
        with _directory(path.parent) as parent:
            raw = _read(parent, path.name, MAX_SOURCE_BYTES)
        if not 1 <= len(raw) <= MAX_SOURCE_BYTES or b"\0" in raw:
            raise ValueError("source must be 1..4096 bytes with no NUL")
        return raw, "supplied_source_file"
    if source_file is None and bundle_root is not None and candidate_id is not None:
        return read_candidate(
            bundle_root, candidate_id
        ).lua_source, "supplied_raw_envelope"
    raise ValueError("supply exactly source_file OR bundle_root and candidate_id")


def _verify(directory, raw, receipt):
    _check_names(directory)
    if _read(directory, "curio.lua", MAX_SOURCE_BYTES) != raw:
        raise ValueError("existing curio.lua conflicts with supplied source")
    if _exists(directory, "curio-used.lua"):
        if _read(directory, "curio-used.lua", MAX_SOURCE_BYTES) != raw:
            raise ValueError("existing curio-used.lua conflicts with supplied source")
    return _json(_read(directory, "curio-install.json", _JSON_CAP), receipt)


def install_saved_source(
    run_directory,
    *,
    source_file=None,
    bundle_root=None,
    candidate_id=None,
    mode="fresh",
):
    """Install before game start, or explicitly verify existing evidence read-only.

    Receipt status describes installation only, including during verification:
    candidate_installed_not_admitted is NOT a claim that native rejection or
    admission has (or has not) happened since installation. No engine events are
    read. Verify does not fill any missing files or retry any failed sync.
    """
    if type(mode) is not str or mode not in ("fresh", "verify"):
        raise ValueError("mode must be fresh or verify")
    # Finish all candidate/resource validation before even creating a run lock.
    raw, provenance = _source(source_file, bundle_root, candidate_id)
    receipt = {
        "version": 1,
        "status": "candidate_installed_not_admitted",
        "source_sha256": _digest(raw),
        "provenance": provenance,
    }
    with _directory(run_directory) as directory:
        with _writer_lock(directory, create=mode == "fresh"):
            _check_names(directory)
            if mode == "fresh":
                if any(_exists(directory, name) for name in _INSTALL_FILES):
                    raise ValueError("existing candidate evidence; fresh game required")
                _publish(directory, "curio.lua", raw)
                # Detect a noncooperating/game writer before claiming installation.
                if _exists(directory, "curio-used.lua"):
                    raise ValueError("game used candidate during pre-game installation")
                _publish(directory, "curio-install.json", _encode(receipt))
            return _verify(directory, raw, receipt)
