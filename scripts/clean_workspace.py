#!/usr/bin/env python3
"""Remove leftover NyarlatHack temporary directories. Dry-run unless --apply.

Candidates are only:

- children of the per-run temp root ``/tmp/nyarlathack-work/``;
- children of ``/tmp`` or ``~/.hermes/cache/scratch`` whose names start with
  ``nyarlathack-`` or ``nyarl-``.

Explicit PATH arguments must be one of those candidates; anything else is
refused. Explicit paths are removed whatever their age (end-of-run cleanup of
your own temp root). Without paths, the allowed roots are scanned and only
items older than ``--max-age`` days (default 7) are removed.

Always skipped: symlinks (never followed), items not owned by the caller,
directories holding a ``KEEP`` marker file, and anything a live process uses
(working directory, root, executable, open file or mapped file under it).
Clones and build trees elsewhere are out of scope: remove them by hand once
their branch is pushed and clean.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import sys
import time

WORK_ROOT = Path("/tmp/nyarlathack-work")
NAME = re.compile(r"^(nyarlathack|nyarl)[-_.]")
KEEP = "KEEP"
DAY = 86400.0


class Roots:
    """work: every child is a candidate; named: only nyarl-named children."""

    def __init__(self, work, named):
        self.work = Path(work)
        self.named = [Path(p) for p in named]


def default_roots():
    return Roots(WORK_ROOT, [Path("/tmp"), Path.home() / ".hermes/cache/scratch"])


def _plain(path):
    """Absolute path with no symlink component anywhere (never followed)."""
    path = Path(os.path.abspath(path))
    return path if os.path.realpath(path) == str(path) else None


def refusal(path, roots):
    """Return why path may not be touched, or None if it is a candidate."""
    if os.path.islink(path):
        return "symlink"
    plain = _plain(path)
    if plain is None:
        return "path goes through a symlink"
    parent = plain.parent
    if parent == roots.work:
        return None
    if parent in roots.named and plain != roots.work:
        return None if NAME.match(plain.name) else "name is not nyarlathack-*/nyarl-*"
    return "outside the allowed NyarlatHack roots"


def candidates(roots):
    found = []
    for root in [roots.work, *roots.named]:
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry == roots.work:
                continue
            if root == roots.work or NAME.match(entry.name):
                found.append(entry)
    return found


def held_paths():
    """Paths live processes use: cwd, root, exe, open files and mappings."""
    held = set()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        for link in ("cwd", "root", "exe"):
            try:
                held.add(os.readlink(proc / link))
            except OSError:
                pass
        try:
            for fd in (proc / "fd").iterdir():
                try:
                    held.add(os.readlink(fd))
                except OSError:
                    pass
        except OSError:
            pass
        try:
            with open(proc / "maps") as maps:
                for line in maps:
                    fields = line.split(None, 5)
                    if len(fields) == 6 and fields[5].startswith("/"):
                        held.add(fields[5].strip())
        except OSError:
            pass
    held.discard("/")
    return held


def in_use(path, held):
    text = str(path)
    return any(h == text or h.startswith(text + "/") for h in held)


def measure(path):
    """Allocated bytes and newest mtime, lstat only; hardlinks counted once."""
    top = os.lstat(path)
    total, newest, seen = top.st_blocks * 512, top.st_mtime, set()
    if not os.path.isdir(path) or os.path.islink(path):
        return total, newest
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            try:
                st = os.lstat(os.path.join(base, name))
            except OSError:
                continue
            if (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            total += st.st_blocks * 512
            newest = max(newest, st.st_mtime)
    return total, newest


def remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)  # unlinks symlinks inside; never follows them
    else:
        os.unlink(path)


def run(paths, *, apply=False, max_age=7.0, roots=None, now=None, out=sys.stdout):
    """Return (exit status, bytes freed or that would be freed)."""
    roots = roots or default_roots()
    now = time.time() if now is None else now
    explicit = bool(paths)
    status = 0
    items = []
    if explicit:
        for raw in paths:
            why = refusal(raw, roots)
            if why:
                print(f"refuse {raw}: {why}", file=out)
                status = 2
            elif not os.path.lexists(raw):
                print(f"absent {raw}", file=out)
            else:
                items.append(Path(os.path.abspath(raw)))
    else:
        items = candidates(roots)
    held = held_paths() if items else set()
    total = 0
    for path in items:
        why = refusal(path, roots)
        if why is None:
            st = os.lstat(path)
            if st.st_uid != os.getuid():
                why = "not owned by this user"
            elif (path / KEEP).exists() if path.is_dir() else False:
                why = "KEEP marker"
            elif in_use(path, held):
                why = "in use by a live process"
        if why:
            print(f"skip {path}: {why}", file=out)
            continue
        size, newest = measure(path)
        age = (now - newest) / DAY
        if not explicit and age < max_age:
            print(f"skip {path}: {age:.1f} days old (< {max_age:g})", file=out)
            continue
        if apply:
            # Re-check immediately before removal: state may have changed.
            if in_use(path, held_paths()) or refusal(path, roots):
                print(f"skip {path}: changed before removal", file=out)
                continue
            remove(path)
        verb = "deleted" if apply else "would delete"
        print(f"{verb} {path} ({size} bytes)", file=out)
        total += size
    verb = "freed" if apply else "would free"
    print(f"{verb} {total} bytes ({total / 1e6:.1f} MB)", file=out)
    return status, total


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Remove leftover NyarlatHack temporary directories."
    )
    parser.add_argument("paths", nargs="*", help="explicit candidates (any age)")
    parser.add_argument("--apply", action="store_true", help="actually delete")
    parser.add_argument(
        "--max-age",
        type=float,
        default=7.0,
        help="days; scan mode only removes older items (default 7)",
    )
    args = parser.parse_args(argv)
    if args.max_age < 0:
        parser.error("--max-age must be non-negative")
    status, _ = run(args.paths, apply=args.apply, max_age=args.max_age)
    return status


if __name__ == "__main__":
    sys.exit(main())
