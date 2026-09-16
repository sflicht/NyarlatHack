"""Cooperative build-receipt adapter, not same-UID cryptographic attestation."""

from dataclasses import dataclass
import json
import re
import subprocess
import sys

from turnloop_dump_provenance import (
    HISTORICAL_REVISION as HISTORICAL_REVISION,
    HISTORICAL_TUPLE,
    _require,
    _sha,
    _unique,
    compare_provenance_dumps,
    validate_build,
    validate_historical_build,
)

PROFILE = {
    "src/version.c": "71bbe8e0b90c09562c41cc5d0cff666ee9fcdf75a5bed2149f9fcb2458ad7b31",
    "src/end.c": "eea94703d918f7a7492ba375ad00432ba7e40fb926cd414d27d21aad6104022e",
    "util/makedefs.c": "0890456ca2f91b017921aba2f84203eb49a43ffc69c221f023ec16131258a6d1",
    "GNUmakefile": "f6cf0fa493dadb27a7470e042bda5e7e7a1f1c304852640d21f8cad751146d80",
    "include/config.h": "6d04d7f3ae172400e0930561acaa2a88b5a7e9e06da2b908673f8b404e1accab",
    "include/unixconf.h": "0bde0712db4ff5aea259d13229cde8bcd9e416865e54c02641c7881f17836a99",
}


def raw_file(path):
    _require(
        not path.is_symlink() and path.is_file(),
        "regular evidence file required: " + str(path),
    )
    return path.read_bytes()


def tuple_bytes(directory):
    return {k: raw_file(directory / k) for k in ("dnethack", "nhdat", "license")}


@dataclass(frozen=True)
class Binding:
    build: object
    sizes: tuple
    evidence: dict

    def verify_tuple(self, directory):
        actual = tuple_bytes(directory)
        for name, digest in self.build.tuple_sha256:
            _require(
                _sha(actual[name]) == digest
                and len(actual[name]) == dict(self.sizes)[name],
                "run/source tuple changed: " + name,
            )
        return self.build


def check_profile(root, revision):
    _require(sys.platform == "linux", "only reviewed Linux profile is supported")
    _require(re.fullmatch("[0-9a-f]{40}", revision) is not None, "full revision")
    head = (
        subprocess.check_output(
            ["/usr/bin/git", "-C", str(root), "rev-parse", "HEAD"], timeout=10
        )
        .decode()
        .strip()
    )
    _require(head == revision, "root HEAD/revision mismatch")
    _require(
        not (root / "local.mk").exists() and not (root / "local.mk").is_symlink(),
        "unsupported local build override",
    )
    for name, digest in PROFILE.items():
        _require(
            _sha(raw_file(root / name)) == digest,
            "unsupported native header profile: " + name,
        )
    return dict(PROFILE)


def current_binding(receipt, directory, revision, mode):
    original = raw_file(receipt / f"{mode}-manifest.json")
    commands_raw = raw_file(receipt / f"{mode}-commands.json")
    m = json.loads(original, object_pairs_hook=_unique)
    commands = json.loads(commands_raw, object_pairs_hook=_unique)
    _require(
        type(m["mode"]) is int and m["mode"] == mode and m["revision"] == revision,
        "receipt revision/mode",
    )
    _require(
        m["commands"] == commands and len(commands) == 2,
        "successful clean/install receipts required",
    )
    for command, target in zip(commands, ("clean", "install")):
        _require(
            type(command["exit_code"]) is int
            and command["exit_code"] == 0
            and command["argv"]
            == [
                "/usr/bin/make",
                "-j2",
                target,
                f"CHAOS={mode}",
                "CC=/usr/bin/cc",
                "PKG_CONFIG=/usr/bin/pkg-config",
            ],
            "unsupported/failed build command",
        )
    actual = tuple_bytes(directory)
    _require(set(m["pairs"]) == set(actual), "receipt tuple set")
    for name, raw in actual.items():
        pair = m["pairs"][name]
        _require(
            type(pair["size"]) is int
            and pair["size"] > 0
            and pair["size"] == len(raw)
            and pair["sha256"] == _sha(raw),
            "receipt tuple hash/size: " + name,
        )
    source = raw_file(receipt / f"{mode}-date.h")
    _require(
        _sha(source) == m["generated_headers"]["include/date.h"], "captured date.h hash"
    )
    definitions = re.findall(
        rb'^#define VERSION_ID \\\n "([\x20-\x21\x23-\x5b\x5d-\x7e]+)"\n',
        source,
        re.MULTILINE,
    )
    _require(
        source.count(b"#define VERSION_ID") == 1 and len(definitions) == 1,
        "unsupported VERSION_ID literal",
    )
    # Only after original receipts, capture and actual tuple have been checked.
    supplemental = json.dumps(
        dict(
            build_name=f"reviewed-chaos{mode}",
            revision=revision,
            mode=mode,
            date_h_sha256=_sha(source),
            tuple_sha256={k: _sha(v) for k, v in actual.items()},
        ),
        sort_keys=True,
    ).encode()
    build = validate_build(
        build_name=f"reviewed-chaos{mode}",
        expected_header=b"Playing " + definitions[0],
        date_h=source,
        manifest=supplemental,
        trusted_manifest_sha256=_sha(supplemental),
        artifacts=actual,
    )
    return Binding(
        build,
        tuple((k, len(v)) for k, v in actual.items()),
        dict(
            original_manifest_hex=original.hex(),
            original_manifest_sha256=_sha(original),
            original_commands_hex=commands_raw.hex(),
            original_commands_sha256=_sha(commands_raw),
            captured_date_h_hex=source.hex(),
            supplemental_manifest_hex=supplemental.hex(),
        ),
    )


def historical_binding(receipt, directory, revision):
    original = raw_file(receipt)
    dump = raw_file(receipt.parent / "game/dumplog/1700000000")
    build = validate_historical_build(
        revision=revision,
        mode=0,
        receipt=original,
        original_dump=dump,
        artifacts=tuple_bytes(directory),
    )
    return Binding(
        build,
        tuple((k, v[1]) for k, v in HISTORICAL_TUPLE.items()),
        dict(
            original_receipt_hex=original.hex(),
            independent_original_dump_hex=dump.hex(),
            original_receipt_path=str(receipt),
        ),
    )


def read_dumps(directory):
    _require(directory.is_dir() and not directory.is_symlink(), "dump directory")
    entries = list(directory.iterdir())
    _require(
        len(entries) == 1 and entries[0].name == "1700000000",
        "exact frozen-route dump filenames/count",
    )
    return {p.name: raw_file(p) for p in entries}


def compare_run(reference, candidate, reference_build, candidate_build):
    for key in ("inputs", "terminal", "xlog"):
        _require(reference[key] == candidate[key], key + " parity")
    return compare_provenance_dumps(
        {k: bytes.fromhex(v) for k, v in reference["dumps"].items()},
        {k: bytes.fromhex(v) for k, v in candidate["dumps"].items()},
        reference_build=reference_build,
        candidate_build=candidate_build,
    )
