#!/usr/bin/env python3
"""Bounded lexical upstream seam audit, not a C parser or physics test.

Discovery is independent of inventory rows. Both CPP branches are scanned.
No writes, compilation, macro expansion, or automatic inventory acceptance.
"""

import argparse
from collections import Counter
from fnmatch import fnmatchcase
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

BASELINE = "a6f0a1c43e66f4fb1bcac34d7d9709706682ec19"
INHERITED = {"chaos_dnum", "chaos_dvariant", "chaos_montype", "CHAOS_S", "CHAOS_SKILL"}
SPECIAL = {
    "curio_tag",
    "inert_bones_curios",
    "financial_unpaid",
    "remember_message",
    "tty_more_presented",
    "tty_update_topl_rendered",
    "tty_display_map_presented",
    "tty_display_nhwindow_impl",
    "tty_putstr_rendered",
    "tty_putstr_core",
    "tty_chaos_echo",
}
TOKEN = re.compile(
    r"(?P<space>[^\S\n]+)|(?P<nl>\n)|(?P<comment>/\*.*?\*/|//[^\n]*)|"
    r'(?P<literal>"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')|'
    r"(?P<id>[A-Za-z_][A-Za-z_0-9]*)|(?P<number>[0-9][A-Za-z_0-9.]*)|"
    r"(?P<punct>[^\w\s])",
    re.S,
)


def lex(text):
    """Return (spelling, kind, logical line); splice before removing comments."""
    text = re.sub(r"\\\r?\n", "", text)
    result, pos, line = [], 0, 1
    while pos < len(text):
        if text.startswith("/*", pos) and "*/" not in text[pos + 2 :]:
            raise ValueError(f"unterminated comment at logical line {line}")
        match = TOKEN.match(text, pos)
        if not match or (text[pos] in "\"'" and match.lastgroup != "literal"):
            raise ValueError(f"invalid token at logical line {line}")
        value, kind = match.group(), match.lastgroup
        if kind not in {"space", "comment", "nl"}:
            result.append((value, kind, line))
        line += value.count("\n")
        pos = match.end()
    return result


def interesting(name):
    return name.startswith(("chaos_", "CHAOS_")) or name == "CHAOS" or name in SPECIAL


@lru_cache(maxsize=512)
def discover(path, text):
    """Discover occurrences with literal-preserving signatures and CPP context."""
    tokens = lex(text)
    values = [t[0] for t in tokens]
    guards, records, inherited = [], [], Counter()
    i = 0
    while i < len(tokens):
        value, kind, line = tokens[i]
        directive = value == "#" and (i == 0 or tokens[i - 1][2] != line)
        if directive:
            end = i + 1
            while end < len(tokens) and tokens[end][2] == line:
                end += 1
            parts = values[i + 1 : end]
            if not parts:
                i = end
                continue
            op = parts[0]
            # Record the controlling expression itself before changing context.
            if (
                any(interesting(t) and t not in INHERITED for t in parts)
                or (op == "include" and any("chaos" in t for t in parts[1:]))
                or (
                    op == "include"
                    and '"wintty.h"' in parts
                    and any("CHAOS" in g for g in guards)
                )
            ):
                records.append(
                    dict(
                        file=path,
                        index=i,
                        line=line,
                        kind="directive",
                        signature=values[i:end],
                        guards=guards.copy(),
                    )
                )
            if op in {"if", "ifdef", "ifndef"}:
                if len(parts) < 2:
                    raise ValueError(f"{path}:{line}: empty conditional")
                guards.append(" ".join(parts))
            elif op in {"else", "elif"}:
                if not guards or "| else" in guards[-1]:
                    raise ValueError(f"{path}:{line}: unmatched/duplicate {op}")
                guards[-1] += " | " + " ".join(parts)
            elif op == "endif":
                if not guards:
                    raise ValueError(f"{path}:{line}: unmatched endif")
                guards.pop()
            # Macro bodies still receive ordinary identifier discovery.
            if op != "define":
                i = end
                continue
        if kind == "id" and value in INHERITED:
            inherited[value] += 1
        elif kind == "id" and interesting(value):
            end = i + 1
            category = "identifier"
            if end < len(tokens) and values[end] == "(":
                depth, end = 1, end + 1
                while end < len(tokens) and depth:
                    depth += (values[end] == "(") - (values[end] == ")")
                    end += 1
                if depth:
                    raise ValueError(f"{path}:{line}: unbalanced hook call {value}")
                category = "call-or-declaration"
            # A short local window also distinguishes surrounding ward/branch seams.
            signature = values[max(0, i - 5) : min(len(tokens), max(end, i + 6))]
            records.append(
                dict(
                    file=path,
                    index=i,
                    line=line,
                    kind=category,
                    signature=signature,
                    guards=guards.copy(),
                )
            )
        # Save-layout bits are not named chaos_* identifiers.
        if path == "util/makedefs.c" and values[i : i + 6] in (
            ["|", "(", "1L", "<", "<", "26"],
            ["|", "(", "1L", "<", "<", "29"],
        ):
            records.append(
                dict(
                    file=path,
                    index=i,
                    line=line,
                    kind="save-feature-bit",
                    signature=values[i : i + 7],
                    guards=guards.copy(),
                )
            )
        i += 1
    if guards:
        raise ValueError(f"{path}: unterminated conditional")
    return records, inherited, values


def git_paths(root, baseline=False):
    command = ["git", "-C", str(root)] + (
        ["ls-tree", "-r", "-z", "--name-only", BASELINE]
        if baseline
        else ["ls-files", "-z"]
    )
    run = subprocess.run(command, capture_output=True, check=False)
    if run.returncode:
        raise ValueError(
            "Git discovery failed; use a Git checkout with full history "
            f"(fetch-depth: 0) and baseline {BASELINE}: "
            + run.stderr.decode(errors="replace").strip()
        )
    return set(run.stdout.decode().split("\0")) - {""}


def scope_paths(tracked, baseline):
    native = {p for p in tracked if p.endswith((".c", ".h"))}
    owned = {
        p
        for p in native - baseline
        if any(
            fnmatchcase(p, pattern)
            for pattern in ("src/chaos_*.c", "include/chaos*.h", "tests/chaos/*")
        )
    }
    return sorted(native - owned), sorted(native - baseline - owned)


def key(row):
    return (
        row["file"],
        row["symbol"],
        row["kind"],
        tuple(row["signature"]),
        tuple(row["guards"]),
    )


def anchor(values, pattern):
    hits = [
        i
        for i in range(len(values) - len(pattern) + 1)
        if values[i : i + len(pattern)] == pattern
    ]
    if len(hits) != 1:
        raise ValueError(
            f"scope anchor must occur exactly once: {pattern!r} ({len(hits)})"
        )
    return hits[0]


def normalized_path(path):
    return (
        isinstance(path, str)
        and bool(path)
        and not PurePosixPath(path).is_absolute()
        and str(PurePosixPath(path)) == path
        and ".." not in PurePosixPath(path).parts
        and "\\" not in path
    )


def validate(data, paths):
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or data["version"] != 1
        or data.get("baseline") != BASELINE
    ):
        raise ValueError("unsupported inventory version or fork baseline")
    for field, kind in [
        ("hooks", list),
        ("windows", dict),
        ("inherited", dict),
        ("build_blocks", list),
    ]:
        if not isinstance(data.get(field), kind):
            raise ValueError(f"invalid inventory {field}")
    for path, windows in data["windows"].items():
        if (
            not normalized_path(path)
            or path not in paths
            or not isinstance(windows, list)
        ):
            raise ValueError(f"invalid window path/list: {path}")
        for window in windows:
            if (
                not isinstance(window, dict)
                or not isinstance(window.get("symbol"), str)
                or not window["symbol"].strip()
            ):
                raise ValueError(f"invalid window symbol: {path}")
            for field in ("start", "end"):
                tokens = window.get(field)
                if (
                    not isinstance(tokens, list)
                    or not all(isinstance(t, str) and t for t in tokens)
                    or (field == "start" and not tokens)
                ):
                    raise ValueError(f"invalid window {field}: {path}")
    for block in data["build_blocks"]:
        if (
            not isinstance(block, list)
            or not block
            or not all(isinstance(x, str) and x for x in block)
        ):
            raise ValueError("invalid build block")
    for path, counts in data["inherited"].items():
        if (
            not normalized_path(path)
            or path not in paths
            or not isinstance(counts, dict)
            or not all(
                k in INHERITED and type(v) is int and v > 0 for k, v in counts.items()
            )
        ):
            raise ValueError(f"invalid inherited counts: {path}")


def check(root, inventory=None, overrides=None, tracked=None, baseline=None):
    """Read-only check; overrides and path lists support in-memory mutant tests."""
    root = Path(root).resolve()
    data = (
        inventory
        if inventory is not None
        else json.loads((root / "docs/upstream-chaos-hooks.json").read_text())
    )
    paths, new = scope_paths(
        git_paths(root) if tracked is None else tracked,
        git_paths(root, True) if baseline is None else baseline,
    )
    validate(data, paths)
    errors = [f"UNCLASSIFIED new native path: {p}" for p in new]
    expected, ids = Counter(), set()
    for row in data["hooks"]:
        p = row["file"]
        if not normalized_path(p) or p not in paths:
            raise ValueError(f"inventory path outside normalized tracked scope: {p}")
        if row["id"] in ids or not isinstance(row["id"], str) or not row["id"]:
            raise ValueError("duplicate or invalid hook ID")
        ids.add(row["id"])
        if type(row["count"]) is not int or row["count"] <= 0:
            raise ValueError("hook count must be a positive integer")
        for field in ("symbol", "purpose", "chaos0", "kind"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"empty metadata: {field}")
        if (
            not isinstance(row["signature"], list)
            or not isinstance(row["guards"], list)
            or not row["signature"]
            or not all(isinstance(x, str) for x in row["signature"] + row["guards"])
        ):
            raise ValueError("invalid token signature/guards")
        expected[key(row)] += row["count"]
    actual, inherited, locations = Counter(), {}, {}
    overrides = overrides or {}
    for path in paths:
        target = root / path
        if (
            not normalized_path(path)
            or target.is_symlink()
            or any(p.is_symlink() for p in target.parents if p != root)
            or not target.resolve().is_relative_to(root)
        ):
            raise ValueError(f"unsafe native path (outside root or symlink): {path}")
        source = (
            overrides[path]
            if path in overrides
            else (root / path).read_text(encoding="latin-1")
        )
        records, old, values = discover(path, source)
        if old:
            inherited[path] = dict(old)
        windows = []
        for window in data.get("windows", {}).get(path, []):
            start = anchor(values, window["start"])
            end = anchor(values, window["end"]) if window["end"] else len(values)
            if end <= start or any(start < b and end > a for a, b, _ in windows):
                raise ValueError(
                    f"invalid/overlapping scope window: {path}:{window['symbol']}"
                )
            windows.append((start, end, window["symbol"]))
        for row in records:
            row = row.copy()
            row["symbol"] = "<file>"
            for a, b, name in windows:
                if a <= row["index"] < b:
                    # Next-declaration windows include inter-function CPP. Only
                    # label directives as local while inside the reviewed body.
                    prefix = values[a : row["index"]]
                    outside = (
                        row["kind"] == "directive"
                        and name != "vpline/pline"
                        and "{" in prefix
                        and prefix.count("{") == prefix.count("}")
                    )
                    if not outside:
                        row["symbol"] = name
                    break
            k = key(row)
            actual[k] += 1
            locations[k] = row["line"]
    if inherited != data["inherited"]:
        errors.append("INHERITED identifier per-file counts drifted")
    for k, count in (actual - expected).items():
        errors.append(f"EXTRA {k[0]}:{locations[k]} {k[1]} {k[2]} count={count} {k[3]}")
    for row in data["hooks"]:
        k = key(row)
        if expected[k] > actual[k]:
            errors.append(
                f"MISSING {row['id']} {k[0]} {k[1]} expected={expected[k]} actual={actual[k]}"
            )
    make = overrides.get("GNUmakefile", (root / "GNUmakefile").read_text())
    make_lines = [
        " ".join(line.split())
        for line in make.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for block in data["build_blocks"]:
        n = len(block)
        if (
            sum(make_lines[i : i + n] == block for i in range(len(make_lines) - n + 1))
            != 1
        ):
            errors.append("BUILD toggle/object block drifted")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    try:
        errors = check(args.root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        errors = [f"INVALID: {exc}"]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Upstream hook inventory: exact lexical coverage verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
