"""Test-only provenance-validated-dump-v1; never replaces strict compare_runs.

The caller independently pins a reviewed manifest digest and supplies the exact
run binary/data/license bytes. Neither the pin nor expected header may originate
from the dump under comparison. See docs/turnloop-dump-comparison-contract.md.
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re


_TUPLE = {"dnethack", "nhdat", "license"}
_SEAL = object()
_HEADER = re.compile(
    rb"Playing dNetHack v[0-9]+(?:\.[0-9]+)+ "
    rb"\(dNAO git [A-Za-z0-9.]+-[0-9]+-g([0-9a-f]{9})\), "
    rb"last build ([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})\."
)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value, length=64):
    return (
        type(value) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    )


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate manifest key")
        result[key] = value
    return result


@dataclass(frozen=True, init=False)
class VerifiedBuild:
    """Immutable factory output, not an arbitrary caller-declared validated dict.

    Python object internals are not a hostile-code security boundary. Only
    validate_build may construct this object in the trusted test process.
    """

    build_name: str
    expected_header: bytes
    revision: str
    mode: int
    manifest_sha256: str
    date_h_sha256: str | None
    tuple_sha256: tuple
    source_kind: str = "generated-date-h"
    history_proof: tuple = ()

    def __init__(self, seal=None, **values):
        _require(seal is _SEAL, "use validate_build with independent evidence")
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def record(self):
        return dict(
            build_name=self.build_name,
            revision=self.revision,
            mode=self.mode,
            expected_header_hex=self.expected_header.hex(),
            manifest_sha256=self.manifest_sha256,
            date_h_sha256=self.date_h_sha256,
            source_kind=self.source_kind,
            history_proof=dict(self.history_proof),
            tuple_sha256=dict(self.tuple_sha256),
        )


def validate_build(
    *, build_name, expected_header, date_h, manifest, trusted_manifest_sha256, artifacts
):
    """Hash-check independent source and actual tuple against a pinned manifest.

    Manifest schema is deliberately supplemental, not a claim about existing
    native receipt fields. Its producer must verify the original mode receipt.
    artifacts maps exactly dnethack/nhdat/license to actual run-file bytes.
    expected_header is a native line WITHOUT its line ending, independently
    provided and cross-checked against generated date.h VERSION_ID content.
    """
    _require(
        type(manifest) is bytes and _digest(trusted_manifest_sha256), "manifest pin"
    )
    _require(_sha(manifest) == trusted_manifest_sha256, "manifest hash mismatch")
    try:
        record = json.loads(manifest, object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed manifest") from exc
    _require(
        type(record) is dict
        and set(record)
        == {"build_name", "revision", "mode", "date_h_sha256", "tuple_sha256"},
        "manifest schema",
    )
    _require(
        type(build_name) is str
        and bool(build_name)
        and record["build_name"] == build_name,
        "build name mismatch",
    )
    _require(type(record["mode"]) is int and record["mode"] in (0, 1), "build mode")
    _require(_digest(record["revision"], 40), "revision")
    _require(
        type(date_h) is bytes and _digest(record["date_h_sha256"]), "date.h evidence"
    )
    _require(_sha(date_h) == record["date_h_sha256"], "date.h hash mismatch")
    _require(type(artifacts) is dict and set(artifacts) == _TUPLE, "actual tuple set")
    hashes = record["tuple_sha256"]
    _require(type(hashes) is dict and set(hashes) == _TUPLE, "manifest tuple set")
    for name in sorted(_TUPLE):
        _require(
            type(artifacts[name]) is bytes and _digest(hashes[name]), "tuple format"
        )
        _require(_sha(artifacts[name]) == hashes[name], name + " identity mismatch")
    _require(type(expected_header) is bytes, "expected header bytes required")
    match = _HEADER.fullmatch(expected_header)
    _require(match is not None, "unsupported native header structure")
    _require(match[1].decode() == record["revision"][:9], "header revision mismatch")
    try:
        datetime.strptime(match[2].decode(), "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("header date") from exc
    # Exact generated form from makedefs.c; no C escapes or general C evaluator.
    definitions = re.findall(
        rb'^#define VERSION_ID \\\n "([^"\r\n]+)"\n', date_h, re.MULTILINE
    )
    _require(
        date_h.count(b"#define VERSION_ID") == 1 and len(definitions) == 1,
        "missing/duplicate/unsupported VERSION_ID",
    )
    _require(expected_header == b"Playing " + definitions[0], "source/header mismatch")
    return VerifiedBuild(
        _SEAL,
        build_name=build_name,
        expected_header=expected_header,
        revision=record["revision"],
        mode=record["mode"],
        manifest_sha256=trusted_manifest_sha256,
        date_h_sha256=record["date_h_sha256"],
        tuple_sha256=tuple(sorted(hashes.items())),
    )


HISTORICAL_REVISION = "ff37b3a7a5381ea9b5d5960dda7bd756c6c8dbd8"
HISTORICAL_RECEIPT = "507aa06667b7041537d377698317575818d22a28030df13441d89316d08daf71"
HISTORICAL_DUMP = "1436059a60659ccf668d30c5c59a115a2c7c8e95875fe9e4c2f3a1e154c077e8"
HISTORICAL_TUPLE = {
    "dnethack": (
        "b5917b5e9f90f52b42d0548da2d03198b72abc395aab2cb30c9f8e7fd9a7b246",
        26481912,
    ),
    "nhdat": (
        "0f6e194353ef46080445ed26a4cbc2cccbad3d751d978f88f5cbb12d84f64b38",
        2197075,
    ),
    "license": (
        "93a3ae2cb8dee482daddfaebe53bcffe5b114b603def19b4dca21621cbc5a747",
        4875,
    ),
}


def validate_historical_build(*, revision, mode, receipt, original_dump, artifacts):
    """Fixed reviewed historical evidence; never manufacture generated source.

    Receipt binds binary/data only. License is a separate reviewed measurement.
    original_dump is the independently pinned OLD recording, not a compared run.
    """
    _require(
        revision == HISTORICAL_REVISION and type(mode) is int and mode == 0,
        "historical revision/mode",
    )
    _require(
        type(receipt) is bytes and _sha(receipt) == HISTORICAL_RECEIPT,
        "historical receipt pin",
    )
    _require(
        type(original_dump) is bytes and _sha(original_dump) == HISTORICAL_DUMP,
        "historical original dump pin",
    )
    record = json.loads(receipt, object_pairs_hook=_unique)
    _require(record["exit"] == 0, "historical exit")
    _require(type(artifacts) is dict and set(artifacts) == _TUPLE, "historical tuple")
    for name, (digest, size) in HISTORICAL_TUPLE.items():
        raw = artifacts[name]
        _require(
            type(raw) is bytes and len(raw) == size and _sha(raw) == digest,
            "historical tuple pin: " + name,
        )
        if name != "license":
            _require(
                record["sessions"][0]["sha256"][name] == digest,
                "historical receipt tuple",
            )
    header = original_dump.split(b"\n")[1]
    _require(
        header
        == b"Playing dNetHack v3.26.0 (dNAO git v3.21.3.1-3193-gff37b3a7a), last build 2026-09-14 03:11:38.",
        "historical header",
    )
    build = VerifiedBuild(
        _SEAL,
        build_name="upstream-stock",
        expected_header=header,
        revision=revision,
        mode=mode,
        manifest_sha256=HISTORICAL_RECEIPT,
        date_h_sha256=None,
        tuple_sha256=tuple(sorted((k, v[0]) for k, v in HISTORICAL_TUPLE.items())),
        source_kind="historical-recorded-dump",
        history_proof=(
            ("original_dump_sha256", HISTORICAL_DUMP),
            (
                "license_binding",
                "separately reviewed pin; absent from original receipt",
            ),
        ),
    )
    _remainder(original_dump, build)
    return build


def _remainder(raw, build):
    _require(type(raw) is bytes, "dump bytes required, not hex/text")
    lines = raw.split(b"\n")
    _require(len(lines) >= 3 and bool(lines[0]), "missing native header line 2")
    candidates = [
        i
        for i, line in enumerate(lines)
        if line.lstrip(b" \t\r").startswith(b"Playing dNetHack")
    ]
    _require(candidates == [1], "missing/duplicate/misplaced native header")
    line = lines[1]
    ending = b"\r" if line.endswith(b"\r") else b""
    content = line[:-1] if ending else line
    _require(content == build.expected_header, "independent header mismatch")
    # Remove ONLY validated identity content; retain both line delimiters,
    # including any CR, all of line 1, binary bytes, and all trailing data.
    lines[1] = ending
    return b"\n".join(lines)


def compare_provenance_dumps(reference, candidate, *, reference_build, candidate_build):
    """Return a separately labelled receipt, or raise ValueError; no I/O.

    Both dump mappings must contain the full filename set and original bytes.
    The caller must enumerate all entries (not silently filter unknown files),
    bind actual run tuples through validate_build, and retain all other oracle
    gates. This is not a whole-run, same-build-repeat, or Task 8 acceptance API.
    """
    for build in (reference_build, candidate_build):
        _require(type(build) is VerifiedBuild, "verified build required")
    if reference_build.build_name == candidate_build.build_name:
        _require(reference_build == candidate_build, "conflicting named build bindings")
    for dumps in (reference, candidate):
        _require(type(dumps) is dict and bool(dumps), "nonempty dump mapping required")
        _require(
            all(
                type(name) is str
                and name not in ("", ".", "..")
                and "/" not in name
                and "\\" not in name
                and "\x00" not in name
                for name in dumps
            ),
            "dump filename",
        )
    _require(set(reference) == set(candidate), "dump filenames/count mismatch")
    for name in sorted(reference):
        left = _remainder(reference[name], reference_build)
        right = _remainder(candidate[name], candidate_build)
        _require(left == right, "dump remainder mismatch: " + name)
        if reference_build.tuple_sha256 == candidate_build.tuple_sha256:
            _require(
                reference[name] == candidate[name], "same-build whole-file mismatch"
            )
    return {
        "comparison": "provenance-validated-dump-v1",
        "equal": True,
        "filenames": sorted(reference),
        "builds": {
            b.build_name: b.record() for b in (reference_build, candidate_build)
        },
    }
