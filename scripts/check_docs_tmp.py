#!/usr/bin/env python3
"""Fail when a tracked file under docs/ cites a /tmp/ path (#176).

/tmp is scratch space and is cleaned, so a /tmp path is not a record. Evidence
goes under docs/evidence/ or into a durable location outside Git, cited by path
plus SHA-256 (docs/workspace-hygiene.md). Historical citations that predate the
rule are listed in scripts/docs_tmp_allowlist.json, per file and per citation,
with a count; their artifacts were moved as recorded in the allowlist's
"mapping". Any citation beyond the allowlist, in a new or changed file, fails.

Read-only. Exit 0 when clean, 1 with one line per excess citation otherwise.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST = ROOT / "scripts" / "docs_tmp_allowlist.json"
CITATION = re.compile(rb"/tmp/[^\s\"'`<>()\[\]{},;\\]*")
MAX_BYTES = 64 << 20


def citations(raw):
    return Counter(m.decode("utf-8", "replace") for m in CITATION.findall(raw))


def tracked_docs(root):
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "docs"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    return sorted(p for p in out.decode().split("\0") if p)


def violations(root, allowlist):
    allowed = allowlist["files"]
    found = []
    for name in tracked_docs(root):
        path = root / name
        if path.is_symlink() or not path.is_file():
            continue
        if path.stat().st_size > MAX_BYTES:
            found.append(f"{name}: too large to scan")
            continue
        seen = citations(path.read_bytes())
        permitted = allowed.get(name, {})
        for cite, count in sorted(seen.items()):
            extra = count - permitted.get(cite, 0)
            if extra > 0:
                found.append(f"{name}: {cite} ({extra} new)")
    return found


def main(argv=None):
    p = argparse.ArgumentParser(description="Fail on new /tmp/ citations in docs/.")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--allowlist", type=Path, default=ALLOWLIST)
    args = p.parse_args(argv)
    allowlist = json.loads(args.allowlist.read_text())
    found = violations(args.root.resolve(), allowlist)
    for line in found:
        print("docs cite /tmp: " + line, file=sys.stderr)
    if found:
        print(
            "Move the artifact under docs/evidence/ or a durable path cited with "
            "its SHA-256 (docs/workspace-hygiene.md, #176).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
