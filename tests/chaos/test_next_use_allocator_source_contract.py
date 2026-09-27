#!/usr/bin/env python3
"""Frozen source-only contract check for N-ID."""
import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path

BASE = {
    "include/flag.h": "da847eca365362522acf77a9ac31d304b2896faa76498f8b2876beaf339480fc",
    "include/extern.h": "601d032e45fbf34dae3664381066b8af2537856cd9a5f9c29804ac2a09475e80",
    "src/allmain.c": "69404381ef519452cf3a0c7183495874586a0248374312aada558f42f5ca281e",
    "src/makemon.c": "2c7c11f1ba66e29513b639f6feca947c79c4575249161e32b7b3855ee1ae45de",
    "src/mkobj.c": "4308b444cc3af80089d1f681920ba9d9e27d009533c859f5b26702398a5e9303",
    "src/restore.c": "3373e69257c2429baec6d19f1eb55523eb22a9afa7e63a558643d4547a976f4a",
    "src/shk.c": "1dccb6edc09bd276c4e29d31a86383b96dd0952b1a0c23e70d1e06e97c8d97da",
}
SITES = (
    ("src/makemon.c", "clone_mon", "m2->m_id", 1),
    ("src/makemon.c", "makemon_core", "mtmp->m_id", 1),
    ("src/mkobj.c", "splitobj", "otmp->o_id", 1),
    ("src/mkobj.c", "duplicate_obj", "otmp->o_id", 1),
    ("src/mkobj.c", "bill_dummy_object", "dummy->o_id", 1),
    ("src/mkobj.c", "mksobj", "otmp->o_id", 1),
    ("src/restore.c", "restobjchn", "nid", 0),
    ("src/restore.c", "restmonchn", "nid", 0),
    ("src/shk.c", "sub_one_frombill", "bp->bo_id = otmp->o_id", 0),
)
LABELS = tuple(x for path, func, lhs, retry in SITES
               for x in (path + ":" + func + ":issue",
                         path + ":" + func + ":zero_retry")[:1 + retry])
LINES = ((13701, 13702), (14594, 14595), (518, 519), (583, 584),
         (698, 699), (729, 730), (235,), (315,), (3022,))
WRITE = re.compile(r"(?:\+\+\s*flags\s*\.\s*ident|--\s*flags\s*\.\s*ident|flags\s*\.\s*ident\s*(?:\+\+|--|[+\-*/%&|^]?=(?!=)))")
SOURCE_ROOTS = ("src", "include", "win", "util", "sys")


def frozen():
    out = []
    label = 0
    for (_path, _func, lhs, retry), lines in zip(SITES, LINES):
        first = ("unsigned " if lhs == "nid" else "") + lhs + " = flags.ident++;"
        out.append((_path, lines[0], first, LABELS[label])); label += 1
        if retry:
            out.append((_path, lines[-1],
                        "if (!" + lhs + ") " + lhs + " = flags.ident++;\t/* ident overflowed */",
                        LABELS[label])); label += 1
    return tuple(out)


BASE_ISSUES = frozen()


def emit(status, code, missing=()):
    print(json.dumps({"checker": "N-ID", "code": code,
        "missing": list(missing), "scope": "source_completeness_only_not_semantic_acceptance",
        "status": status}, sort_keys=True, separators=(",", ":")))


def scrub(text):
    out = list(text)
    i = 0
    state = "code"
    quote = ""
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if state == "code" and c == "/" and n == "*":
            out[i] = out[i + 1] = " "; i += 2; state = "block"; continue
        if state == "code" and c == "/" and n == "/":
            out[i] = out[i + 1] = " "; i += 2; state = "line"; continue
        if state == "code" and c in "\"'":
            quote = c; out[i] = " "; i += 1; state = "string"; continue
        if state == "block":
            if c == "*" and n == "/":
                out[i] = out[i + 1] = " "; i += 2; state = "code"; continue
            if c != "\n": out[i] = " "
            i += 1; continue
        if state == "line":
            if c == "\n": state = "code"
            else: out[i] = " "
            i += 1; continue
        if state == "string":
            if c == "\\" and i + 1 < len(text):
                out[i] = out[i + 1] = " "; i += 2; continue
            if c == quote: state = "code"
            if c != "\n": out[i] = " "
            i += 1; continue
        i += 1
    return "".join(out)


def matching(text, start, opening, closing):
    depth = 0
    for pos in range(start, len(text)):
        if text[pos] == opening:
            depth += 1
        elif text[pos] == closing:
            depth -= 1
            if depth == 0:
                return pos
    return -1


def kr_declarations(text):
    """Recognize K&R parameter declarations without swallowing a later body."""
    parts = [part.strip() for part in text.split(";") if part.strip()]
    if not parts:
        return False
    declaration = re.compile(
        r"^(?:(?:register|const|volatile)\s+)*(?:struct\s+\w+|union\s+\w+|enum\s+\w+|unsigned|signed|short|long|int|char|boolean|void|xchar)\b",
        re.S)
    for part in parts:
        part = re.sub(r"^\s*#.*?$", "", part, flags=re.M).strip()
        if not declaration.match(part):
            return False
    return True


def function_ranges(text, name):
    clean = scrub(text)
    found = []
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", clean):
        opened = clean.find("(", match.start())
        closed = matching(clean, opened, "(", ")")
        if closed < 0:
            continue
        pos = closed + 1
        while pos < len(clean) and clean[pos].isspace():
            pos += 1
        if pos >= len(clean) or clean[pos] in ";,":
            continue
        if clean[pos] == "{":
            start = pos
        else:
            start = clean.find("{", pos, min(len(clean), pos + 4000))
            if start < 0 or not kr_declarations(clean[pos:start]):
                continue
        end = matching(clean, start, "{", "}")
        if end >= 0:
            found.append((match.start(), end + 1, start, end + 1,
                          clean[start:end + 1]))
    return found


def body(text, name):
    found = function_ranges(text, name)
    return found[0][4] if len(found) == 1 else None


def statement_end(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return -1
    if text[start] == "{":
        return matching(text, start, "{", "}")
    parens = brackets = 0
    for pos in range(start, len(text)):
        c = text[pos]
        if c == "(": parens += 1
        elif c == ")": parens -= 1
        elif c == "[": brackets += 1
        elif c == "]": brackets -= 1
        elif c == ";" and parens == 0 and brackets == 0:
            return pos
    return -1


def if_regions(text):
    out = []
    for match in re.finditer(r"\bif\s*\(", text):
        opened = text.find("(", match.start())
        closed = matching(text, opened, "(", ")")
        if closed < 0:
            continue
        end = statement_end(text, closed + 1)
        if end >= 0:
            out.append((match.start(), end + 1,
                        text[opened + 1:closed], text[closed + 1:end + 1]))
    return out


def for_regions(text):
    out = []
    for match in re.finditer(r"\bfor\s*\(\s*;\s*;\s*\)", text):
        end = statement_end(text, match.end())
        if end >= 0:
            out.append((match.start(), end + 1, text[match.end():end + 1]))
    return out


def chaos_regions(text):
    """Return textual ranges controlled by a preprocessor CHAOS condition."""
    lines = text.splitlines(keepends=True)
    stack = []
    regions = []
    offset = 0
    for line in lines:
        directive = re.match(r"\s*#\s*(if|ifdef|ifndef|endif)\b(.*)", line)
        if directive:
            kind, rest = directive.group(1), directive.group(2)
            if kind in ("if", "ifdef", "ifndef"):
                is_chaos = bool(re.search(r"\bCHAOS\b", rest)) and kind != "ifndef"
                stack.append((offset, is_chaos))
            elif stack:
                start, is_chaos = stack.pop()
                if is_chaos:
                    regions.append((start, offset + len(line)))
        offset += len(line)
    return regions


def pat(lhs, callee):
    lhs = re.escape(lhs).replace(r"\ ", r"\s*")
    return re.compile(lhs + r"\s*=\s*" + callee + r"\s*\(\s*\)\s*;")


def texts(root):
    """Read the bounded, regular, non-symlink production C/H inventory."""
    out = {}

    def visit(directory):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            mode = path.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                continue
            if stat.S_ISDIR(mode):
                visit(path)
            elif stat.S_ISREG(mode) and path.suffix in (".c", ".h"):
                out[path.relative_to(root).as_posix()] = path.read_bytes().decode("latin-1")

    for name in SOURCE_ROOTS:
        base = root / name
        try:
            mode = base.stat(follow_symlinks=False).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise OSError("invalid source inventory root: " + name)
        visit(base)
    return out


def allocator_hazard_contract(helper):
    """Prove the finite CHAOS-only skip of one armed reserved identity."""
    issue = re.search(r"\b(\w+)\s*=\s*flags\s*\.\s*ident\s*\+\+\s*;", helper)
    if not issue or len(WRITE.findall(helper)) != 1:
        return False
    issued = issue.group(1)
    returned = re.search(r"\breturn\s+" + re.escape(issued) + r"\s*;", helper)
    if returned is None:
        return False
    loops = [region for region in for_regions(helper)
             if region[0] < issue.start() < region[1] and region[0] < returned.start() < region[1]]
    if len(loops) != 1:
        return False

    regions = chaos_regions(helper)
    if len(regions) != 1:
        return False
    chaos_start, chaos_end = regions[0]
    if not (issue.end() <= chaos_start < chaos_end <= returned.start()):
        return False
    chaos = helper[chaos_start:chaos_end]

    assignments = []
    for match in re.finditer(r"\b(\w+)\s*=\s*([^;]+);", chaos):
        assignments.append((match.group(1), match.group(2), match.start()))
    wrapped = next(((name, chaos_start + pos) for name, expr, pos in assignments
                    if ((re.search(r"flags\s*\.\s*ident\s*==\s*0", expr) or
                         re.search(r"!\s*flags\s*\.\s*ident\b", expr) or
                         re.search(r"flags\s*\.\s*ident\s*<\s*" + re.escape(issued) + r"\b", expr) or
                         re.search(r"\b" + re.escape(issued) + r"\s*==\s*UINT_MAX\b", expr))
                        and not re.search(r"\bcontinue\b", expr))), None)
    reserved = next(((name, chaos_start + pos) for name, expr, pos in assignments
                     if (re.search(r"\b" + re.escape(issued) + r"\b", expr)
                         and "==" in expr
                         and re.search(r"\b(?:armed|active|W_ARMED)\b", expr, re.I)
                         and re.search(r"\b(?:reserved|captured|target|identity|m_id|w_id)\w*\b", expr, re.I))), None)
    if not wrapped or not reserved:
        return False
    wrapped_name, wrapped_pos = wrapped
    reserved_name, reserved_pos = reserved

    mark_calls = list(re.finditer(r"\bchaos_next_use_mark_identity_unsafe\s*\(\s*\)\s*;", helper))
    if len(mark_calls) != 1 or not (chaos_start <= mark_calls[0].start() < chaos_end):
        return False
    hazard = None
    for start, end, condition, statement in if_regions(helper):
        if start <= mark_calls[0].start() < end:
            if (re.search(r"\b" + re.escape(wrapped_name) + r"\b", condition)
                    and re.search(r"\b" + re.escape(reserved_name) + r"\b", condition)
                    and "||" in condition):
                hazard = (start, end, condition, statement)
                break
    if hazard is None or max(wrapped_pos, reserved_pos) >= hazard[0]:
        return False

    guarded_continue = False
    for start, end, condition, statement in if_regions(helper):
        if hazard[0] <= start and end <= hazard[1] and re.search(r"\bcontinue\s*;", statement):
            if re.search(r"\b" + re.escape(reserved_name) + r"\b", condition):
                guarded_continue = True
    if not guarded_continue or len(re.findall(r"\bcontinue\s*;", helper)) != 1:
        return False
    if re.search(r"(?:\b" + re.escape(issued) + r"\b|flags\s*\.\s*ident)\s*==\s*0[^;{}]*continue", helper):
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    root = Path(parser.parse_args().root)
    if not root.is_dir():
        emit("ERROR", "INVALID_ROOT")
        return 2
    paths = {name: root / name for name in BASE}
    if any(not path.is_file() for path in paths.values()):
        emit("ERROR", "MISSING_ALLOCATOR_FIXTURE_PATH")
        return 2
    try:
        raw = {name: path.read_bytes() for name, path in paths.items()}
        own = {name: data.decode("utf-8") for name, data in raw.items()}
        prod = texts(root)
    except (OSError, UnicodeError):
        emit("ERROR", "UNREADABLE_ALLOCATOR_SOURCE")
        return 2
    clean = {name: scrub(text) for name, text in prod.items()}
    writes = [(name, source.count("\n", 0, match.start()) + 1)
              for name, source in clean.items() for match in WRITE.finditer(source)]
    helper = body(own["src/allmain.c"], "next_ident")

    if helper is None and not any("next_ident" in source for source in own.values()):
        expected = {(name, line) for name, line, _source, _label in BASE_ISSUES}
        expected.add(("src/allmain.c", 4196))
        exact = all(own[name].splitlines()[line - 1].strip() == source
                    for name, line, source, _label in BASE_ISSUES)
        exact &= own["src/allmain.c"].splitlines()[4195].strip() == "flags.ident = 1;"
        exact &= "unsigned ident;\t\t/* social security number for each monster */" in own["include/flag.h"]
        if set(writes) != expected:
            extra = sorted("%s:%d" % item for item in set(writes) - expected)
            if extra:
                emit("RED", "UNCLASSIFIED_IDENT_WRITER", extra)
                return 1
            exact = False
        if not exact or any(hashlib.sha256(raw[name]).hexdigest() != digest
                            for name, digest in BASE.items()):
            emit("ERROR", "R1_0_ALLOCATOR_CLOSURE_MISMATCH")
            return 2
        emit("RED", "UNROUTED_ID_ISSUERS", LABELS)
        return 1

    missing = []
    unrouted = []
    known_direct = 0
    routed = 0
    definitions = [(name, item[0]) for name, source in prod.items()
                   for item in function_ranges(source, "next_ident")]
    if len(definitions) != 1 or definitions[0][0] != "src/allmain.c":
        missing.append("NEXT_IDENT_EXACT_DEFINITION_OWNER")

    declaration_pattern = re.compile(
        r"(?:unsigned\s+next_ident\s*\(\s*void\s*\)|"
        r"unsigned\s+NDECL\s*\(\s*next_ident\s*\))\s*;")
    declarations = [(name, match.start(), match.end())
                    for name, source in clean.items()
                    for match in declaration_pattern.finditer(source)]
    if len(declarations) != 1 or declarations[0][0] != "include/extern.h":
        missing.append("NEXT_IDENT_EXACT_DECLARATION_INVENTORY")

    expected_calls = set()
    for path, func, lhs, retry in SITES:
        ranges = function_ranges(prod[path], func)
        if len(ranges) != 1:
            continue
        function = ranges[0]
        for match in pat(lhs, "next_ident").finditer(function[4]):
            callee = re.search(r"\bnext_ident\s*\(", match.group())
            if callee:
                expected_calls.add((path, function[2] + match.start() + callee.start()))

    definition_starts = {(name, pos) for name, pos in definitions}
    declaration_spans = {}
    for name, start, end in declarations:
        declaration_spans.setdefault(name, []).append((start, end))
    actual_calls = set()
    for name, source in clean.items():
        for match in re.finditer(r"\bnext_ident\s*\(", source):
            if (name, match.start()) in definition_starts:
                continue
            if any(start <= match.start() < end
                   for start, end in declaration_spans.get(name, ())):
                continue
            actual_calls.add((name, match.start()))
    if len(actual_calls) != 15 or actual_calls != expected_calls:
        missing.append("NEXT_IDENT_COMPLETE_CALL_MULTISET_15")

    for path, func, lhs, retry in SITES:
        function = body(own[path], func) or ""
        need = 2 if retry else 1
        direct = len(re.findall(re.escape(lhs).replace(r"\ ", r"\s*") +
                                r"\s*=\s*flags\s*\.\s*ident\s*\+\+\s*;", function))
        known_direct += direct
        calls = len(pat(lhs, "next_ident").findall(function))
        routed += calls
        first = path + ":" + func + ":issue"
        second = path + ":" + func + ":zero_retry"
        if direct or calls != need:
            unrouted.append(first)
        if retry and not re.search(r"if\s*\(\s*!\s*" + re.escape(lhs) + r"\s*\)\s*" +
                                   re.escape(lhs) + r"\s*=\s*next_ident\s*\(\s*\)", function):
            unrouted.append(second)
        if not retry and re.search(r"if\s*\(\s*!\s*(?:nid|bp->bo_id|otmp->o_id)", function):
            missing.append("NO_RETRY_SITE_CHANGED_" + func)

    init = len(re.findall(r"flags\s*\.\s*ident\s*=\s*1\s*;", clean["src/allmain.c"]))
    helper_writes = 0 if helper is None else len(WRITE.findall(helper))
    if len(writes) != init + helper_writes + known_direct:
        emit("RED", "UNCLASSIFIED_IDENT_WRITER", sorted({name for name, _line in writes}))
        return 1
    if unrouted:
        emit("RED", "UNROUTED_ID_ISSUERS", tuple(dict.fromkeys(unrouted)))
        return 1

    ext = scrub(own["include/extern.h"])
    if not declaration_pattern.search(ext):
        missing.append("NEXT_IDENT_DECLARATION")
    if helper is None:
        missing.append("NEXT_IDENT_DEFINITION")
    else:
        issued = re.search(r"\b(\w+)\s*=\s*flags\s*\.\s*ident\s*\+\+\s*;", helper)
        if helper_writes != 1 or not issued:
            missing.append("NEXT_IDENT_EXACT_ONE_POSTINCREMENT")
        elif not re.search(r"\breturn\s+" + re.escape(issued.group(1)) + r"\s*;", helper):
            missing.append("NEXT_IDENT_RETURNS_ISSUED_VALUE")
        if not allocator_hazard_contract(helper):
            missing.append("CHAOS_ARMED_RESERVED_ID_FINITE_ADVANCE")
        if re.search(r"(?:\b\w+\b|flags\s*\.\s*ident)\s*==\s*0[^;{}]*(?:continue|flags\s*\.\s*ident\s*\+\+)", helper):
            missing.append("NEXT_IDENT_GLOBAL_ZERO_SKIP")

    if init != 1:
        missing.append("NEWGAME_IDENT_INITIALIZATION")
    if routed != 15:
        missing.append("ROUTED_ISSUER_COUNT_15")
    owners = "\n".join(scrub(own[name]) for name in BASE)
    if any(re.search(pattern, owners, re.I) for pattern in (
            r"chaos_next_use_end_w", r"\bend_w\s*\(", r"target_registry",
            r"chaos_next_use_take_identity_unsafe",
            r"\b(?:identity|target)_map\b", r"identity_epoch", r"saved_epoch")):
        missing.append("FORBIDDEN_ALLOCATOR_RUNTIME_OWNERSHIP")

    if missing:
        emit("RED", "INCOMPLETE_ALLOCATOR_SLICE", tuple(dict.fromkeys(missing)))
        return 1
    emit("GREEN", "ALLOCATOR_SLICE_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("ERROR", "CHECKER_ERROR_" + type(exc).__name__.upper())
        sys.exit(2)
