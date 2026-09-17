"""Read-only shared native job selection; not a provenance replacement.

The trusted runner selects the descriptor, checkout and full revision independently
of receipts. Stable cooperating files only, not hostile same-UID attestation.
Native drivers still verify source/header/object identity and calibrate as before.
"""

import json
import os
from pathlib import Path
import re
import stat

KEY = "NYARLATHACK_NATIVE_DESCRIPTOR"
REVISION_KEY = "NYARLATHACK_NATIVE_EXPECTED_REVISION"
FAMILIES = {
    "platform": "PLATFORM",
    "whistle": "WHISTLE",
    "fountain": "FOUNTAIN",
    "fountain-matrix": "FOUNTAIN",
    "action-transport": "ACTION_TRANSPORT",
    "delivery": "NATIVE",
    "history": "NATIVE",
    "turnloop": "TURNLOOP",
}
FIELDS = {
    "schema",
    "root",
    "revision",
    "receipt",
    "build_output",
    "artifact_parent",
    "profile",
    "historical_stock",
}


class ConfigurationError(ValueError, AssertionError):
    """Explicit invalid configuration must fail, never become a skip."""


def require(value, message):
    if not value:
        raise ConfigurationError(message)


def canonical(value):
    require(
        type(value) is str and value and not any(c in value for c in "\0\n\r"),
        "invalid path",
    )
    path = Path(value)
    require(
        path.is_absolute()
        and str(path) == value
        and ".." not in path.parts
        and path.resolve() == path,
        "canonical absolute path without symlinks required",
    )
    return path


def private_directory(value):
    path = canonical(str(value))
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700,
        "owned private 0700 directory required",
    )
    return path


def revision(value):
    require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value),
        "independent revision must be full lowercase 40hex",
    )


def _pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate descriptor key")
        result[key] = value
    return result


def load(path, root, expected_revision):
    """Check bounded JSON against independent job context, without launching."""
    revision(expected_revision)
    path = canonical(str(path))
    private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600,
            "descriptor must be owned private 0600 regular single-link file",
        )
        raw = stream.read(16385)
    require(len(raw) <= 16384, "descriptor too large")
    try:
        data = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: require(False, "non-JSON constant"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError("invalid descriptor JSON") from exc
    require(
        type(data) is dict and set(data) == FIELDS,
        "unknown or incomplete descriptor schema",
    )
    require(
        type(data["schema"]) is int and data["schema"] == 1,
        "unknown descriptor schema version",
    )
    require(
        data["root"] == str(root)
        and canonical(data["root"]) == Path(__file__).resolve().parents[2],
        "descriptor root must match actual test checkout",
    )
    require(
        data["revision"] == expected_revision,
        "descriptor revision differs from independent job revision",
    )
    for field in ("receipt", "build_output", "artifact_parent"):
        private_directory(data[field])
    require(data["profile"] in ("core", "selected-turnloop"), "unknown native profile")
    stock = data["historical_stock"]
    if data["profile"] == "core":
        require(stock is None, "core forbids historical-stock context")
    else:
        require(
            type(stock) is dict and set(stock) == {"tuple", "receipt", "revision"},
            "complete historical stock selection required",
        )
        canonical(stock["tuple"])
        canonical(stock["receipt"])
        revision(stock["revision"])
    return data


def enabled(name, environment=None):
    """A descriptor opts in; legacy execution flags retain their semantics.

    Oracle evidence and source/archive selection alone do not authorize a game.
    Even an empty descriptor value enters validation and fails, never skips.
    """
    env = os.environ if environment is None else environment
    require(name in FAMILIES, "unregistered native family")
    flag = (
        "NYARLATHACK_TURNLOOP_TESTS" if name == "turnloop" else "NYARLATHACK_GAME_TESTS"
    )
    return KEY in env or env.get(flag) == "1"


def family(name, root, environment=None):
    env = os.environ if environment is None else environment
    require(name in FAMILIES, "unregistered native family")
    prefix = "NYARLATHACK_" + FAMILIES[name] + "_"
    if KEY not in env:
        keys = ("ROOT", "RECEIPT", "REVISION", "ARTIFACTS")
        if name == "fountain-matrix":
            keys = ("ROOT", "RECEIPT", "REVISION", "MATRIX_ARTIFACTS")
        if name in ("platform", "turnloop"):
            keys += ("OFF_TUPLE",)
        if not any(prefix + k in env for k in keys):
            return None
        for key in keys:
            require(
                env.get(prefix + key),
                "complete explicit native family configuration required: "
                + prefix
                + key,
            )
        result = {k.lower().replace("_", "-"): env[prefix + k] for k in keys}
        if name == "fountain-matrix":
            result["artifacts"] = result.pop("matrix-artifacts")
        return result
    require(
        not any(
            k.startswith("NYARLATHACK_" + p + "_")
            for k in env
            for p in ("PLATFORM", "WHISTLE", "FOUNTAIN", "ACTION_TRANSPORT", "TURNLOOP")
            if k
            not in (
                "NYARLATHACK_TURNLOOP_EVIDENCE",
                "NYARLATHACK_TURNLOOP_STOCK_TUPLE",
                "NYARLATHACK_TURNLOOP_STOCK_RECEIPT",
                "NYARLATHACK_TURNLOOP_STOCK_REVISION",
            )
        ),
        "mixed descriptor and legacy family configuration",
    )
    data = load(env[KEY], root, env.get(REVISION_KEY))
    for key, expected in (
        ("NYARLATHACK_NATIVE_FIXTURE_MODE", "source-build"),
        ("NYARLATHACK_NATIVE_BUILD_RECEIPT", data["receipt"]),
        ("NYARLATHACK_GAME_TESTS", "1"),
    ):
        require(
            key not in env or env[key] == expected, "conflicting common native context"
        )
    if name == "turnloop" and data["profile"] == "core":
        return None
    leaf = Path(data["artifact_parent"]) / name
    require(not os.path.lexists(leaf), "artifact leaf must be absent")
    result = dict(
        root=data["root"],
        receipt=data["receipt"],
        revision=data["revision"],
        artifacts=str(leaf),
    )
    if name in ("platform", "turnloop"):
        result["off-tuple"] = str(Path(data["build_output"]) / "stock")
    if name == "turnloop":
        result.update({"stock-" + k: v for k, v in data["historical_stock"].items()})
    return result


def arguments(name, root, environment=None):
    value = family(name, root, environment)
    require(value is not None, "complete explicit native configuration required")
    return value, [part for key, val in value.items() for part in ("--" + key, val)]
