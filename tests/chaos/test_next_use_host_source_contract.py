#!/usr/bin/env python3
"""Frozen source-only contract check for N-HOST-STATE."""
import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path

BASELINE = {
    "include/chaos.h": "6f88c919c2785ecb830b0aa69bd87d47ef1a430cce3f23ed48761dc0bdaa07e9",
    "src/chaos_engine.c": "0f14d4709a0027b670e62aad5f0100fc7d4e44cc75e790614e0733850737c151",
}
BRIDGE = (
    "chaos_observation_begin_exclusive",
    "chaos_observation_finish",
    "chaos_next_use_whistle_completed",
    "chaos_next_use_fountain_contact",
    "chaos_next_use_fountain_clear",
)
DECLARATIONS = (
    r"boolean\s+chaos_observation_begin_exclusive\s*\(\s*int\s+operation\s*,\s*long\s*\*\s*root_out\s*\)\s*;",
    r"boolean\s+chaos_observation_finish\s*\(\s*long\s+root\s*,\s*int\s+stage\s*,\s*long\s*\*\s*end_seq_out\s*\)\s*;",
    r"void\s+chaos_next_use_whistle_completed\s*\(\s*struct\s+obj\s*\*\s*obj\s*,\s*long\s+completed_root\s*\)\s*;",
    r"boolean\s+chaos_next_use_fountain_contact\s*\(\s*long\s+completed_root\s*,\s*struct\s+chaos_fountain_token\s*\*\s*token_out\s*\)\s*;",
    r"void\s+chaos_next_use_fountain_clear\s*\(\s*struct\s+chaos_fountain_token\s*\*\s*token\s*\)\s*;",
)
ADMISSION_DECLS = (
    "chaos_next_use_reserve",
    "chaos_next_use_debit",
    "chaos_next_use_admit",
    "chaos_next_use_append_private",
    "chaos_next_use_deliver_receipt",
)
FORBIDDEN_DEFINITIONS = (
    "chaos_next_use_jcs",
    "chaos_next_use_sha256",
    "chaos_next_use_reserve",
    "chaos_next_use_debit",
    "chaos_next_use_admit",
    "chaos_next_use_append_private",
    "chaos_next_use_deliver_receipt",
    "chaos_next_use_on_action",
    "chaos_next_use_end_w",
    "chaos_next_use_on_manifestation",
    "chaos_next_use_expire",
    "chaos_next_use_replay_record",
    "chaos_next_use_mark_identity_unsafe",
    "chaos_next_use_take_identity_unsafe",
)
ALTERNATES = ("next_use_w_manifestation", "w_manifestation")
FALSE_RETURN = r"\breturn\s+(?:0|FALSE)\s*;"
TRUE_RETURN = r"\breturn\s+(?:1|TRUE)\s*;"
ANY_FAILURE_RETURN = r"\breturn(?:\s+(?:0|FALSE))?\s*;"
SOURCE_ROOTS = ("src", "include", "win", "util", "sys")


def emit(status, code, missing=()):
    print(json.dumps({"checker": "N-HOST-STATE", "code": code,
        "missing": list(missing), "scope": "source_completeness_only_not_semantic_acceptance",
        "status": status}, sort_keys=True, separators=(",", ":")))


def source_texts(root):
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
                name = path.relative_to(root).as_posix()
                out[name] = path.read_bytes().decode("latin-1")

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


def scrub_c(text):
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
    """Accept old-style parameter declarations, not an unrelated call tail."""
    parts = [part.strip() for part in text.split(";") if part.strip()]
    if not parts:
        return False
    decl = re.compile(r"^(?:(?:register|const|volatile)\s+)*(?:struct\s+\w+|union\s+\w+|enum\s+\w+|unsigned|signed|short|long|int|char|boolean|void)\b", re.S)
    return all(decl.match(re.sub(r"^\s*#.*?$", "", part, flags=re.M).strip()) for part in parts)


def function_ranges(text, name):
    clean = scrub_c(text)
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
            found.append((match.start(), end + 1, clean[start:end + 1]))
    return found


def function_body(text, name):
    found = function_ranges(text, name)
    return found[0][2] if len(found) == 1 else None


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


def if_regions(body):
    regions = []
    for match in re.finditer(r"\bif\s*\(", body):
        opened = body.find("(", match.start())
        closed = matching(body, opened, "(", ")")
        if closed < 0:
            continue
        end = statement_end(body, closed + 1)
        if end >= 0:
            regions.append((match.start(), end + 1,
                            body[opened + 1:closed], body[closed + 1:end + 1]))
    return regions


def calls(body, name):
    found = []
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", body):
        opened = body.find("(", match.start())
        closed = matching(body, opened, "(", ")")
        if closed >= 0:
            found.append((match.start(), closed + 1, body[opened + 1:closed]))
    return found


def guarded_failure(body, before, required=(), return_pattern=FALSE_RETURN):
    for start, _end, condition, statement in if_regions(body):
        if start >= before or not re.search(return_pattern, statement):
            continue
        if all(re.search(pattern, condition, re.S) for pattern in required):
            return start
    return -1


def call_failure_guard(body, call):
    return any(start <= call[0] < end and re.search(FALSE_RETURN, statement)
               and re.search(r"!\s*chaos_io_observation\s*\(", condition)
               for start, end, condition, statement in if_regions(body))


def in_constant_dead_branch(body, call):
    return any(start <= call[0] < end and re.fullmatch(r"\s*(?:0|FALSE)\s*", condition)
               for start, end, condition, _statement in if_regions(body))


def validate_begin(body):
    if not body:
        return False
    io_calls = calls(body, "chaos_io_observation")
    if len(io_calls) != 1:
        return False
    io = io_calls[0]
    if not all(term in io[2] for term in (
            "CHAOS_OBS_OP_WHISTLE_ATTENTION", "CHAOS_OBS_STAGE_STARTED",
            "CHAOS_OBS_FACT_NONE")):
        return False
    op_guard = guarded_failure(body, io[0],
        (r"\boperation\b", r"CHAOS_OBS_OP_WHISTLE_ATTENTION", r"!="))
    root_guard = guarded_failure(body, io[0],
        (r"(?:\bobservation_root\s*(?:!=\s*0|>\s*0)|\bobservation_root\b(?!\s*(?:==\s*0|<=\s*0)))",))
    out_guard = guarded_failure(body, io[0], (r"!\s*root_out\b",))
    root_regions = [(start, end, statement) for start, end, condition, statement
                    in if_regions(body)
                    if re.search(r"\bobservation_root\b", condition)]
    zero_writes = [match.start() for match in re.finditer(
        r"\*\s*root_out\s*=\s*0L?\s*;", body)]
    nested_zero = any(re.search(r"\*\s*root_out\s*=\s*0L?\s*;", statement)
                      and re.search(FALSE_RETURN, statement)
                      for _start, _end, statement in root_regions)
    zero_after_nesting = any(end < position < op_guard
                             for _start, end, _statement in root_regions
                             for position in zero_writes)
    first_write = re.search(r"(?:\*\s*root_out|\bobservation_(?:root|turn|operation|pending|used|blocked))\s*=", body)
    if (min(op_guard, root_guard, out_guard) < 0 or not nested_zero
            or not zero_after_nesting
            or (first_write and root_guard > first_write.start())):
        return False
    if "observation_clear" in body or not call_failure_guard(body, io):
        return False
    root_set = re.search(r"\b(\w+)\s*=\s*u\s*\.\s*chaos\s*\.\s*seq\s*;", body[io[1]:])
    if not root_set:
        return False
    root_name = root_set.group(1)
    root_pos = io[1] + root_set.start()
    nonzero = guarded_failure(body, len(body),
        (r"\b" + re.escape(root_name) + r"\b", r"(?:!\s*" + re.escape(root_name) + r"\b|<=\s*0|==\s*0)"))
    publication = re.search(r"\*\s*root_out\s*=\s*" + re.escape(root_name) + r"\s*;", body)
    own_root = (root_name == "observation_root" or
        re.search(r"\bobservation_root\s*=\s*" + re.escape(root_name) + r"\s*;", body[root_pos:]))
    own_op = re.search(r"\bobservation_operation\s*=\s*CHAOS_OBS_OP_WHISTLE_ATTENTION\s*;", body[root_pos:])
    own_turn = re.search(r"\bobservation_turn\s*=\s*moves\s*;", body[root_pos:])
    if nonzero < root_pos or not publication or publication.start() <= nonzero:
        return False
    return bool(own_root and own_op and own_turn and
                re.search(TRUE_RETURN, body[publication.end():]))


def validate_finish(body):
    if not body:
        return False
    io_calls = calls(body, "chaos_io_observation")
    if len(io_calls) != 1:
        return False
    io = io_calls[0]
    if not all(term in io[2] for term in (
            "CHAOS_OBS_OP_WHISTLE_ATTENTION", "stage", "root",
            "CHAOS_OBS_FACT_NONE")):
        return False
    root_guard = guarded_failure(body, io[0],
        (r"\broot\b", r"\bobservation_root\b", r"!="))
    positive_guard = guarded_failure(body, io[0],
        (r"\broot\b", r"(?:<=\s*0|!\s*root\b)"))
    out_guard = guarded_failure(body, io[0], (r"!\s*end_seq_out\b",))
    stage_guard = guarded_failure(body, io[0],
        (r"\bstage\b", r"CHAOS_OBS_STAGE_COMPLETED", r"CHAOS_OBS_STAGE_BLOCKED"))
    zero_output = re.search(r"\*\s*end_seq_out\s*=\s*0L?\s*;", body)
    if (min(root_guard, positive_guard, out_guard, stage_guard) < 0
            or not zero_output
            or zero_output.start() >= min(root_guard, positive_guard, stage_guard)):
        return False
    if not call_failure_guard(body, io):
        return False
    clear_calls = calls(body, "observation_clear")
    if len(clear_calls) != 1 or clear_calls[0][0] <= io[1]:
        return False
    direct = re.search(r"\*\s*end_seq_out\s*=\s*u\s*\.\s*chaos\s*\.\s*seq\s*;", body)
    local = re.search(r"\b(\w+)\s*=\s*u\s*\.\s*chaos\s*\.\s*seq\s*;", body[io[1]:])
    end_write = direct
    if not end_write and local:
        name = local.group(1)
        end_write = re.search(r"\*\s*end_seq_out\s*=\s*" + re.escape(name) + r"\s*;", body)
    if not end_write or not (io[1] <= end_write.start() < clear_calls[0][0]):
        return False
    return bool(re.search(TRUE_RETURN, body[clear_calls[0][1]:]))


def validate_whistle(body):
    if not body:
        return False
    action = calls(body, "chaos_next_use_on_action")
    if len(action) != 1 or "completed_root" not in action[0][2] or in_constant_dead_branch(body, action[0]):
        return False
    obj_guard = guarded_failure(body, action[0][0],
        (r"(?:!\s*obj\b|\bobj\b\s*==\s*(?:0|NULL))",), ANY_FAILURE_RETURN)
    root_guard = guarded_failure(body, action[0][0],
        (r"(?:completed_root\s*<=\s*0|!\s*completed_root\b)",), ANY_FAILURE_RETURN)
    return min(obj_guard, root_guard) >= 0


def validate_contact(body):
    if not body:
        return False
    action = calls(body, "chaos_next_use_on_action")
    if (len(action) != 1 or not all(x in action[0][2] for x in ("completed_root", "token_out"))
            or in_constant_dead_branch(body, action[0])):
        return False
    token_guard = guarded_failure(body, action[0][0], (r"!\s*token_out\b",))
    root_guard = guarded_failure(body, action[0][0],
        (r"(?:completed_root\s*<=\s*0|!\s*completed_root\b)",))
    fields = {
        "root": r"token_out\s*->\s*root\s*=\s*0L?\s*;",
        "active": r"token_out\s*->\s*active\s*=\s*0\s*;",
        "remap": r"token_out\s*->\s*remap\s*=\s*0\s*;",
        "consumed": r"token_out\s*->\s*consumed\s*=\s*0\s*;",
    }
    positions = []
    for pattern in fields.values():
        match = re.search(pattern, body)
        if not match:
            return False
        positions.append(match.start())
    returns_active = re.search(r"\breturn\s+token_out\s*->\s*active\s*;", body[action[0][1]:])
    return (min(token_guard, root_guard) >= 0 and max(positions) < action[0][0]
            and bool(returns_active))


def validate_clear(body):
    if not body:
        return False
    null_guard = guarded_failure(body, len(body), (r"!\s*token\b",), ANY_FAILURE_RETURN)
    memset = re.search(r"\bmemset\s*\(\s*token\s*,\s*0\s*,\s*sizeof\s*\(?\s*\*\s*token\s*\)?\s*\)\s*;", body)
    assignments = all(re.search(r"token\s*->\s*" + field + r"\s*=\s*0L?\s*;", body)
                      for field in ("root", "active", "remap", "consumed"))
    return null_guard >= 0 and bool(memset or assignments)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        emit("ERROR", "INVALID_ROOT")
        return 2
    base_paths = {name: root / name for name in BASELINE}
    if any(not path.is_file() for path in base_paths.values()):
        emit("ERROR", "MISSING_HOST_FIXTURE_PATH")
        return 2
    try:
        raw = {name: path.read_bytes() for name, path in base_paths.items()}
        header = raw["include/chaos.h"].decode("utf-8")
        engine = raw["src/chaos_engine.c"].decode("utf-8")
    except (OSError, UnicodeError):
        emit("ERROR", "UNREADABLE_HOST_SOURCE")
        return 2

    missing_bridge = [name for name in BRIDGE if name not in header + engine]
    if missing_bridge == list(BRIDGE):
        if any(hashlib.sha256(raw[name]).hexdigest() != digest
               for name, digest in BASELINE.items()):
            emit("ERROR", "BASELINE_HOST_HASH_MISMATCH")
            return 2
        emit("RED", "MISSING_HOST_BRIDGE_SLICE", BRIDGE)
        return 1

    try:
        inventory = source_texts(root)
    except (OSError, UnicodeError):
        emit("ERROR", "UNREADABLE_HOST_SOURCE")
        return 2

    dependency_names = (
        "include/chaos_next_use_contract.h",
        "include/chaos_protocol.h",
        "include/chaos_next_use_admission.h",
    )
    dependency_paths = {name: root / name for name in dependency_names}
    missing = []
    if any(not path.is_file() for path in dependency_paths.values()):
        missing.append("HOST_DEPENDENCY_DECLARATIONS")
        deps = {}
    else:
        try:
            deps = {name: path.read_text(encoding="utf-8")
                    for name, path in dependency_paths.items()}
        except (OSError, UnicodeError):
            emit("ERROR", "UNREADABLE_HOST_DEPENDENCY_SOURCE")
            return 2

    bodies = {}
    for name, pattern in zip(BRIDGE, DECLARATIONS):
        if not re.search(pattern, scrub_c(header), re.S):
            missing.append("DECLARATION_" + name)
        bodies[name] = function_body(engine, name)
        if bodies[name] is None:
            missing.append("DEFINITION_" + name)
        if header.count(name) < 2:
            missing.append("CHAOS_OFF_SURFACE_" + name)
        definitions = [(path, item[0]) for path, text in inventory.items()
                       for item in function_ranges(text, name)]
        if len(definitions) != 1 or definitions[0][0] != "src/chaos_engine.c":
            missing.append("SOLE_HOST_DEFINITION_" + name)

    if deps:
        shared = deps["include/chaos_next_use_contract.h"]
        protocol = deps["include/chaos_protocol.h"]
        admission = deps["include/chaos_next_use_admission.h"]
        if not all(term in shared for term in (
                "struct chaos_fountain_token", "struct chaos_whistle_certificate",
                "chaos_next_use_mark_identity_unsafe",
                "chaos_next_use_take_identity_unsafe")):
            missing.append("SHARED_CONTRACT_DECLARATIONS")
        if not all(term in protocol for term in (
                "CHAOS_OBS_OP_WHISTLE_ATTENTION", "whistle_attention",
                "CHAOS_OBS_FACT_ATTENTION", "attention")):
            missing.append("PROTOCOL_DEPENDENCY_DECLARATIONS")
        if not all(term in admission for term in ADMISSION_DECLS):
            missing.append("ADMISSION_DEPENDENCY_DECLARATIONS")
        if "chaos_next_use_contract.h" not in header:
            missing.append("SHARED_CONTRACT_INCLUDE")

    begin, finish, whistle, contact, clear = (bodies[name] or "" for name in BRIDGE)
    legacy_begin = function_body(engine, "chaos_observation_begin") or ""
    legacy_end = function_body(engine, "chaos_observation_end") or ""
    legacy_clear = calls(legacy_begin, "observation_clear")
    legacy_io = calls(legacy_end, "chaos_io_observation")
    if (not legacy_clear or guarded_failure(legacy_begin, legacy_clear[0][0],
            (r"\boperation\b", r"CHAOS_OBS_OP_WHISTLE_ATTENTION", r"==")) < 0):
        missing.append("LEGACY_BEGIN_REJECTS_EXCLUSIVE_OPERATION3")
    if (not legacy_io or guarded_failure(legacy_end, legacy_io[0][0],
            (r"\bobservation_operation\b", r"CHAOS_OBS_OP_WHISTLE_ATTENTION", r"=="),
            ANY_FAILURE_RETURN) < 0):
        missing.append("LEGACY_END_REJECTS_EXCLUSIVE_OPERATION3")
    if begin and not validate_begin(begin):
        missing.append("EXCLUSIVE_BEGIN_LIVE_OPERATION3_START")
    if finish and not validate_finish(finish):
        missing.append("FINISH_MATCHED_SAME_ROOT_END_CLEAR")
    if whistle and not validate_whistle(whistle):
        missing.append("WHISTLE_LIVE_RUNTIME_TRANSITION")
    if contact and not validate_contact(contact):
        missing.append("FOUNTAIN_CONTACT_LIVE_TOKEN_TRANSITION")
    if clear and not validate_clear(clear):
        missing.append("FOUNTAIN_CLEAR_WRITES_ALL_FIELDS")

    for name in FORBIDDEN_DEFINITIONS:
        if function_body(engine, name) is not None:
            missing.append("FORBIDDEN_HOST_IMPLEMENTATION_" + name)
    for match in re.finditer(r"\b(chaos_next_use_parse_[A-Za-z0-9_]+|luaL?_[A-Za-z0-9_]+)\s*\(", scrub_c(engine)):
        if function_body(engine, match.group(1)) is not None:
            missing.append("FORBIDDEN_HOST_INTERFACE_IMPLEMENTATION")
            break
    if re.search(r"\bcallback_ordinal\s*(?:\+\+|--|[+\-*/%&|^]?=(?!=))", scrub_c(engine)):
        missing.append("FORBIDDEN_HOST_CALLBACK_ORDINAL_WRITE")
    if any(alt in header + engine for alt in ALTERNATES):
        missing.append("FORBIDDEN_ALTERNATE_ROOT_IDENTITY")

    if missing:
        emit("RED", "MISSING_HOST_BRIDGE_SLICE", tuple(dict.fromkeys(missing)))
        return 1
    emit("GREEN", "HOST_BRIDGE_SLICE_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("ERROR", "CHECKER_ERROR_" + type(exc).__name__.upper())
        sys.exit(2)
