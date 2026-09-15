"""Read-only verifier for the reviewed local system-gcc13 builder receipts.

Caller must independently select a trusted, owned/private receipt directory, the
clean checkout and a reviewed full revision. This is cooperating-writer local
trust, NOT authentication of arbitrary JSON or protection against malicious
same-UID writers/races. Do not use preservation paths to select build artifacts.
Only source/build input identity is returned: no ELF/ABI, driver, compression,
copy/runtime identity or gameplay acceptance. Mode 0 inputs were overwritten by
mode 1 and cannot be verified here. No fallback, environment selection or pins.
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess


class IdentityError(ValueError):
    """Selected receipts or current source/build inputs violate the contract."""


@dataclass(frozen=True)
class SourceBuildInputs:
    build_root: Path
    tuple_dir: Path
    mode: int
    revision: str
    artifact_hashes: dict
    metadata: dict
    limits: str = (
        "source/build input identity only; native ABI calibration still separate"
    )


def _require(condition, message):
    if not condition:
        raise IdentityError(message)


def _keys(value, keys, label):
    _require(
        type(value) is dict and set(value) == set(keys.split()),
        f"{label}: incorrect fields",
    )


def _text(value, label):
    _require(
        type(value) is str and bool(value.strip()) and "\x00" not in value,
        f"{label}: expected nonempty string",
    )


def _hex(value, length, label):
    _require(
        type(value) is str and re.fullmatch("[0-9a-f]{" + str(length) + "}", value),
        f"{label}: invalid full hexadecimal identity",
    )


def _time(value):
    _text(value, "timestamp")
    try:
        _require(
            datetime.fromisoformat(value).utcoffset() is not None,
            "timestamp: timezone required",
        )
    except ValueError as exc:
        raise IdentityError("invalid timestamp") from exc


def _regular(path, private=False):
    for part in (path, *path.parents):
        _require(not part.is_symlink(), f"symlink path: {part}")
    info = path.stat()
    _require(
        stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
        f"not a single-link regular file: {path}",
    )
    if private:
        _require(
            info.st_uid == os.getuid() and not info.st_mode & 0o077,
            f"receipt must be owned/private: {path}",
        )
    return info


def _pairs_no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value, f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _load(root, name):
    path = root / name
    _regular(path, private=True)
    return json.loads(
        path.read_text(),
        object_pairs_hook=_pairs_no_duplicates,
        parse_constant=lambda value: _require(False, f"invalid JSON constant: {value}"),
    )


def _digest(path):
    _regular(path)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _relative(root, name):
    _text(name, "input path")
    p = PurePosixPath(name)
    _require(
        not p.is_absolute()
        and ".." not in p.parts
        and str(p) == name
        and name != "."
        and "\\" not in name,
        f"noncanonical input path: {name}",
    )
    path = root / name
    _regular(path)
    _require(path.resolve().is_relative_to(root), f"input escapes build root: {name}")
    return path


def _inputs(root, recorded, kind):
    _require(
        type(recorded) is dict and bool(recorded), f"{kind}: empty/invalid input set"
    )
    # Match reviewed builder's include/*.h and recursive src/util/sys/win *.o.
    roots = ("include",) if kind == "headers" else ("src", "util", "sys", "win")
    actual = set()

    def traversal_error(error):
        raise error

    for directory in roots:
        top = root / directory
        _require(
            top.is_dir() and not top.is_symlink(), f"invalid input directory: {top}"
        )
        for current, directories, files in os.walk(top, onerror=traversal_error):
            for child in directories:
                _require(
                    not (Path(current) / child).is_symlink(), "symlink input directory"
                )
            for child in files:
                path = Path(current) / child
                if path.suffix == (".h" if kind == "headers" else ".o"):
                    # Nested headers are unsupported by this builder's manifest.
                    _require(
                        kind != "headers" or path.parent == top,
                        "unrecorded nested header",
                    )
                    actual.add(str(path.relative_to(root)))
    for name, digest in recorded.items():
        _hex(digest, 64, kind + " hash")
        _require(
            _digest(_relative(root, name)) == digest, f"{kind} hash mismatch: {name}"
        )
    _require(set(recorded) == actual, f"{kind}: incomplete or extra input set")
    return len(actual)


def _git(root, *args):
    # Fixed trusted binary/arguments; no receipt command is ever executed.
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout.strip()


def verify_source_build(receipt_dir, build_root, expected_revision, *, mode=1):
    """Return validated source/build inputs, NOT permission to launch native code.

    Accepts the actual parent builder shape (no invented schema sentinels).
    Receipt logs/symbols are historical metadata, not ELF measurements. Source
    provenance relies on that trusted builder's clean-build procedure; receipt
    ownership alone cannot prove how artifacts were compiled. Keep inputs stable
    while checking and independently recheck copied artifacts before any launch.
    """
    _hex(expected_revision, 40, "expected revision")  # before any Git lookup
    _require(
        type(mode) is int and mode == 1, "unsupported mode: only mode 1 inputs retained"
    )
    try:
        return _verify(
            Path(receipt_dir).absolute(), Path(build_root).absolute(), expected_revision
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        if isinstance(exc, IdentityError):
            raise
        raise IdentityError(f"invalid source-build inputs: {exc}") from exc


def _verify(receipts, root, revision):
    _require(
        receipts.is_dir() and not receipts.is_symlink(), "invalid receipt directory"
    )
    info = receipts.stat()
    _require(
        info.st_uid == os.getuid() and not info.st_mode & 0o077,
        "receipt directory must be owned/private",
    )
    _require(
        root.is_dir() and not root.is_symlink() and root == root.resolve(),
        "build root must be canonical and not symlinked",
    )
    pre = _load(receipts, "preflight.json")
    manifest = _load(receipts, "1-manifest.json")
    commands = _load(receipts, "1-commands.json")
    done = _load(receipts, "completion.json")
    _keys(
        pre,
        "revision tree environment started_eastern compiler pkg_flags protected disk_free",
        "preflight",
    )
    _keys(
        manifest,
        "mode revision pairs symbols generated_headers objects commands finished_eastern acceptance",
        "manifest",
    )
    _keys(
        done,
        "finished_modes protected_unchanged protected_after finished_eastern disk_free",
        "completion",
    )
    _require(
        type(manifest["mode"]) is int and manifest["mode"] == 1,
        "manifest mode mismatch",
    )
    _require(
        pre["revision"]
        == manifest["revision"]
        == revision
        == _git(root, "rev-parse", "HEAD"),
        "revision mismatch",
    )
    _hex(pre["tree"], 40, "preflight tree")
    _require(pre["tree"] == _git(root, "rev-parse", "HEAD^{tree}"), "tree mismatch")
    _require(
        not _git(root, "status", "--porcelain", "--untracked-files=no"),
        "dirty tracked tree; clean required",
    )
    _require(
        all(
            entry.startswith("H ")
            for entry in _git(root, "ls-files", "-v", "-z").split("\x00")
            if entry
        ),
        "unsupported index flags; clean tracked inspection required",
    )
    _require(not os.path.lexists(root / "local.mk"), "local.mk override forbidden")
    _regular(root / ".chaos-build")
    _require(
        (root / ".chaos-build").read_text().strip() == "1", "build mode marker mismatch"
    )
    env = pre["environment"]
    _keys(env, "PATH HOME LANG TZ PKG_CONFIG_LIBDIR", "environment")
    _text(env["HOME"], "HOME")
    _require(Path(env["HOME"]).is_absolute(), "HOME must be absolute")
    _require(
        {k: v for k, v in env.items() if k != "HOME"}
        == {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TZ": "America/New_York",
            "PKG_CONFIG_LIBDIR": "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig",
        },
        "unsupported system environment profile",
    )
    _text(pre["compiler"], "compiler")
    _require(
        pre["compiler"].splitlines()[0] == "cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0",
        "unsupported compiler receipt profile",
    )
    _text(pre["pkg_flags"], "pkg_flags")
    _require(
        pre["pkg_flags"].split()
        == [
            "-I/usr/include/lua5.4",
            "-D_DEFAULT_SOURCE",
            "-D_XOPEN_SOURCE=600",
            "-llua5.4",
            "-lncursesw",
            "-ltinfo",
        ],
        "unsupported pkg_flags",
    )
    for record, field in (
        (pre, "started_eastern"),
        (manifest, "finished_eastern"),
        (done, "finished_eastern"),
    ):
        _time(record[field])
    for record in (pre, done):
        _require(
            type(record["disk_free"]) is int and record["disk_free"] >= 0,
            "invalid disk_free",
        )
    _require(
        type(done["finished_modes"]) is list
        and all(type(m) is int for m in done["finished_modes"])
        and done["finished_modes"] == [0, 1],
        "incomplete builder completion",
    )
    _require(
        done["protected_unchanged"] is True
        and done["protected_after"] == pre["protected"],
        "preservation receipt mismatch",
    )
    _require(
        type(pre["protected"]) is dict and bool(pre["protected"]),
        "invalid preservation record",
    )
    for path, digest in pre["protected"].items():
        _require(Path(path).is_absolute(), "invalid preservation path")
        _hex(digest, 64, "preservation hash")  # Never open these original-host paths.
    _require(
        type(commands) is list
        and len(commands) == 2
        and json.dumps(manifest["commands"], sort_keys=True)
        == json.dumps(commands, sort_keys=True),
        "command receipts disagree or incomplete",
    )
    for command, target in zip(commands, ("clean", "install")):
        _keys(command, "argv log started_eastern finished_eastern exit_code", "command")
        _require(
            command["argv"]
            == [
                "/usr/bin/make",
                "-j2",
                target,
                "CHAOS=1",
                "CC=/usr/bin/cc",
                "PKG_CONFIG=/usr/bin/pkg-config",
            ],
            "unsupported build command metadata",
        )
        _require(
            type(command["exit_code"]) is int and command["exit_code"] == 0,
            "unsuccessful build receipt",
        )
        _text(command["log"], "command log")
        _require(
            Path(command["log"]).is_absolute(), "command log must be absolute metadata"
        )
        _time(command["started_eastern"])
        _time(command["finished_eastern"])
    _require(
        type(manifest["symbols"]) is list
        and all(type(s) is str for s in manifest["symbols"]),
        "invalid symbols metadata",
    )
    _require(
        manifest["acceptance"]
        == "Build and binary identity only; no gameplay or tests",
        "unexpected receipt acceptance scope",
    )
    headers = _inputs(root, manifest["generated_headers"], "headers")
    objects = _inputs(root, manifest["objects"], "objects")
    _keys(manifest["pairs"], "dnethack nhdat license", "artifact pairs")
    hashes = {}
    for name, source in [
        ("dnethack", "src/dnethack"),
        ("nhdat", "dat/nhdat"),
        ("license", "dat/license"),
    ]:
        pair = manifest["pairs"][name]
        _keys(pair, "sha256 size", "artifact")
        _hex(pair["sha256"], 64, "artifact hash")
        _require(
            type(pair["size"]) is int and pair["size"] > 0, "invalid artifact size"
        )
        for relative in (source, "dnethackdir/" + name):
            path = _relative(root, relative)
            _require(
                path.stat().st_size == pair["size"] and _digest(path) == pair["sha256"],
                f"artifact identity mismatch: {relative}",
            )
        hashes[name] = pair["sha256"]
    return SourceBuildInputs(
        root,
        root / "dnethackdir",
        1,
        revision,
        hashes,
        {
            "receipt_dir": str(receipts),
            "profile": "system-gcc13-local",
            "compiler_receipt": pre["compiler"],
            "environment": env,
            "header_count": headers,
            "object_count": objects,
            "tree": pre["tree"],
        },
    )
