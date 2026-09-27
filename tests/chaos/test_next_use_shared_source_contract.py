#!/usr/bin/env python3
"""Frozen source-only contract check for S-SHARED-CONTRACTS."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

EXPECTED = b"#ifndef CHAOS_NEXT_USE_CONTRACT_H\n#define CHAOS_NEXT_USE_CONTRACT_H\n\nstruct chaos_fountain_token {\n    long root;\n    int active;\n    int remap;\n    int consumed;\n};\n\nstruct chaos_whistle_certificate {\n    long root;\n    long notice_seq;\n    long end_seq;\n    int completed;\n    int published;\n};\n\nvoid chaos_next_use_mark_identity_unsafe(void);\nint chaos_next_use_take_identity_unsafe(void);\n\n#endif\n"
EXPECTED_SHA256 = "0c8d2c9582c212229f55f5eb7afa0d15b3ec9133bafbb565f69e8e05183cde35"
DECLARATIONS = (
    b"struct chaos_fountain_token",
    b"struct chaos_whistle_certificate",
    b"chaos_next_use_mark_identity_unsafe",
    b"chaos_next_use_take_identity_unsafe",
)


def emit(status, code, missing=()):
    print(json.dumps({"checker":"S-SHARED-CONTRACTS","code":code,"missing":list(missing),"scope":"source_completeness_only_not_semantic_acceptance","status":status}, sort_keys=True, separators=(",", ":")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        emit("ERROR", "INVALID_ROOT")
        return 2
    path = root / "include/chaos_next_use_contract.h"
    if not path.exists():
        emit("RED", "MISSING_SHARED_CONTRACT_HEADER", ("MISSING_SHARED_CONTRACT_HEADER",))
        return 1
    try:
        data = path.read_bytes()
    except OSError:
        emit("ERROR", "UNREADABLE_SHARED_CONTRACT_HEADER")
        return 2
    missing = []
    if data != EXPECTED:
        missing.append("SHARED_CONTRACT_EXACT_BYTES")
    if hashlib.sha256(data).hexdigest() != EXPECTED_SHA256:
        missing.append("SHARED_CONTRACT_SHA256")
    if tuple(item for item in DECLARATIONS if data.count(item) == 1) != DECLARATIONS:
        missing.append("SHARED_CONTRACT_DECLARATION_KEYSET")
    if missing:
        emit("RED", "INCOMPLETE_SHARED_CONTRACT_HEADER", missing)
        return 1
    emit("GREEN", "SHARED_CONTRACT_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("ERROR", "CHECKER_ERROR_" + type(exc).__name__.upper())
        sys.exit(2)
