#!/usr/bin/env python3
"""Structural I-RUNTIME-REPLAY source gate; never compiles or imports candidates."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = {
    "GNUmakefile": "f6cf0fa493dadb27a7470e042bda5e7e7a1f1c304852640d21f8cad751146d80",
    "src/chaos_engine.c": "0f14d4709a0027b670e62aad5f0100fc7d4e44cc75e790614e0733850737c151",
}
NEW = ("include/chaos_next_use_runtime.h", "src/chaos_next_use_runtime.c")
HOOKS = (
    "chaos_next_use_on_action",
    "chaos_next_use_end_w",
    "chaos_next_use_on_manifestation",
    "chaos_next_use_expire",
    "chaos_next_use_replay_record",
    "chaos_next_use_mark_identity_unsafe",
    "chaos_next_use_take_identity_unsafe",
)
ENGINE_HOOKS = ("chaos_next_use_on_action", "chaos_next_use_on_manifestation")
W_STATES = (
    "UNDECLARED", "PENDING", "CONSUMED_ARMED", "CONSUMED_QUIET",
    "CONSUMED_DELAY", "CONSUMED_INVALID", "CONSUMED_SUPPRESSED",
    "TERMINATED_EXPIRY", "TERMINATED_LEVEL", "TERMINATED_TRANSPORT",
)
F_STATES = (
    "UNDECLARED", "PENDING", "CONSUMED_APPLIED", "CONSUMED_NONREMAPPABLE",
    "CONSUMED_QUIET", "CONSUMED_DELAY", "CONSUMED_INVALID",
    "CONSUMED_SUPPRESSED", "TERMINATED_EXPIRY", "TERMINATED_LEVEL",
    "TERMINATED_TRANSPORT",
)
W_RUNTIME = (
    "INACTIVE", "ARMED", "WINDOW_ENDED", "EXPIRED", "DEPARTED",
    "IDENTITY_UNSAFE", "INVALID_TERMINATED", "TRANSPORT_TERMINATED",
)
END_ROWS = {
    "WINDOW_A_PLUS_10": (False, ("W_ENDED_AFTER_WITNESS", "W_ENDED_NO_WITNESS"), "WINDOW_ENDED"),
    "LEVEL_DEPARTURE": (False, ("W_ENDED_AFTER_WITNESS", "W_ENDED_NO_WITNESS"), "DEPARTED"),
    "ORIGIN_EVICTED": (False, ("W_ENDED_AFTER_WITNESS", "W_ENDED_NO_WITNESS"), "EXPIRED"),
    "ORIGIN_EXPIRED": (False, ("W_ENDED_AFTER_WITNESS", "W_ENDED_NO_WITNESS"), "EXPIRED"),
    "PROGRAM_EXPIRED": (False, ("W_ENDED_AFTER_WITNESS", "W_ENDED_NO_WITNESS"), "EXPIRED"),
    "INVALID_CALLBACK": (True, ("W_ENDED_AFTER_WITNESS", "W_ENDED_NO_WITNESS"), "INVALID_TERMINATED"),
    "IDENTITY_UNSAFE": (True, ("W_IDENTITY_UNSAFE",), "IDENTITY_UNSAFE"),
}
PRIVATE_FIELDS = {
    "at_move", "data", "kind", "next_use_private_v", "program_id", "seq", "source_sha256",
}
PUBLIC_FIELDS = {"end_seq", "family", "next_use_public_v", "notice_seq", "phase", "root"}
TERMINATION_FIELDS = {"failure_code", "reason", "slot_f", "slot_w", "w_runtime"}
PRIVATE_KINDS = ("attempt", "admission", "intent", "effect", "termination")


def emit(status, code, missing=()):
    print(json.dumps({
        "checker": "I-RUNTIME-REPLAY",
        "code": code,
        "missing": list(missing),
        "scope": "source_completeness_only_not_semantic_acceptance",
        "status": status,
    }, sort_keys=True, separators=(",", ":")))


def scrub(text, literals=True):
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    if literals:
        text = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', "", text)
    return text


def balanced(text, start, opening, closing):
    depth = 0
    for pos in range(start, len(text)):
        if text[pos] == opening:
            depth += 1
        elif text[pos] == closing:
            depth -= 1
            if depth == 0:
                return text[start:pos + 1], pos + 1
    return "", -1


def function_body(text, name):
    clean = scrub(text, literals=False)
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", clean):
        opening = clean.find("(", match.start())
        _, after = balanced(clean, opening, "(", ")")
        if after < 0:
            continue
        tail = clean[after:]
        nonspace = len(tail) - len(tail.lstrip())
        if tail[nonspace:].startswith(";"):
            continue
        brace = clean.find("{", after, after + 1200)
        if brace < 0 or clean[after:brace].strip():
            continue
        result, _ = balanced(clean, brace, "{", "}")
        if result:
            return result
    return ""


def enum_members(text, label):
    clean = scrub(text)
    found = []
    pattern = re.compile(r"(?:typedef\s+)?enum(?:\s+([A-Za-z_]\w*))?\s*\{(.*?)\}\s*([A-Za-z_]\w*)?\s*;", re.S)
    for match in pattern.finditer(clean):
        names = " ".join(x or "" for x in (match.group(1), match.group(3))).lower()
        if label.lower() not in names:
            continue
        members = []
        for item in match.group(2).split(","):
            name = item.split("=", 1)[0].strip()
            identifier = re.match(r"([A-Za-z_]\w*)$", name)
            if identifier:
                members.append(identifier.group(1))
        found.append(tuple(members))
    return found


def normalized_exact(members, expected):
    normalized = []
    for member in members:
        hits = [state for state in expected if member == state or member.endswith("_" + state)]
        if len(hits) != 1:
            return False
        normalized.append(hits[0])
    return tuple(normalized) == expected


def struct_fields(text, label):
    clean = scrub(text)
    results = []
    pattern = re.compile(r"struct\s+([A-Za-z_]\w*)\s*\{", re.S)
    for match in pattern.finditer(clean):
        if label.lower() not in match.group(1).lower():
            continue
        block, _ = balanced(clean, clean.find("{", match.start()), "{", "}")
        if not block:
            continue
        fields = []
        depth = 0
        current = ""
        for char in block[1:-1]:
            depth += (char == "{") - (char == "}")
            if char == ";" and depth == 0:
                identifiers = re.findall(r"\b([A-Za-z_]\w*)\b", current)
                if identifiers:
                    fields.append(identifiers[-1])
                current = ""
            else:
                current += char
        results.append(set(fields))
    return results


def switch_cases(body):
    result = {}
    matches = list(re.finditer(r"\bcase\s+([A-Za-z_]\w*)\s*:", body))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        default = re.search(r"\bdefault\s*:", body[match.end():end])
        if default:
            end = match.end() + default.start()
        result[match.group(1)] = body[match.end():end]
    return result


def row_case(cases, reason):
    hits = [(name, value) for name, value in cases.items() if name == reason or name.endswith("_" + reason)]
    return hits[0][1] if len(hits) == 1 else ""


def root_check(branch, required):
    predicates = re.findall(r"\bif\s*\(([^)]*)\)", branch, re.S)
    root_predicates = [p for p in predicates if "root" in p and re.search(r"==|!=", p)]
    if not root_predicates:
        return False
    joined = " ".join(root_predicates)
    has_null = bool(re.search(r"\b(?:NULL|0)\b", joined))
    if not has_null:
        return False
    # Root-required and root-forbidden rows must reject the opposite polarity.
    wanted = r"(?:==\s*(?:NULL|0)|!\s*root\b)" if required else r"(?:!=\s*(?:NULL|0)|\broot\b\s*(?![=!]))"
    return bool(re.search(wanted, joined)) and any(re.search(r"\b(?:return|goto)\b", p + branch) for p in root_predicates)


def call_positions(body, word):
    return [m.start() for m in re.finditer(r"\b[A-Za-z_]\w*" + word + r"[A-Za-z_]*\s*\(", body, re.I)]


def if_conditions(body):
    out = []
    for match in re.finditer(r"\bif\s*\(", body):
        opening = body.find("(", match.start())
        condition, after = balanced(body, opening, "(", ")")
        if condition:
            out.append((match.start(), after, condition[1:-1]))
    return out


def guarded_replay(body):
    mutation = re.search(r"(?:->|\.)\s*(?:slot_[wf]|w_runtime|state|seq|callback_ordinal)\s*(?:=|\+\+|\+=|--|-\=)", body)
    limit = mutation.start() if mutation else len(body)
    required = {"root", "hash", "ordinal", "state", "seq"}
    seen = set()
    for start, after, condition in if_conditions(body):
        if start >= limit or not re.search(r"==|!=|<=|>=|<|>", condition):
            continue
        tail = body[after:min(limit, after + 500)]
        if not re.search(r"\b(?:return|goto)\b", tail) or "BLOCKED_REPLAY" not in tail:
            continue
        for key in required:
            if re.search(r"\b\w*" + key + r"\w*\b", condition, re.I):
                seen.add(key)
    conjunction = any(
        all(re.search(r"\b\w*" + key + r"\w*\b", condition, re.I) for key in required)
        and condition.count("&&") >= 4
        for start, _, condition in if_conditions(body) if start < limit
    )
    return seen == required and (conjunction or len([c for s, _, c in if_conditions(body) if s < limit]) >= 5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    root = Path(parser.parse_args().root)
    if not root.is_dir():
        emit("ERROR", "INVALID_ROOT")
        return 2
    baseline_paths = {name: root / name for name in BASE}
    if any(not path.is_file() for path in baseline_paths.values()):
        emit("ERROR", "MISSING_RUNTIME_FIXTURE_PATH")
        return 2
    try:
        baseline_raw = {name: path.read_bytes() for name, path in baseline_paths.items()}
        baseline = {name: value.decode("utf-8") for name, value in baseline_raw.items()}
    except (OSError, UnicodeError):
        emit("ERROR", "UNREADABLE_RUNTIME_BASE_SOURCE")
        return 2
    candidates = [root / name for name in NEW]
    if all(not path.exists() for path in candidates) and not any(
        hook in baseline["src/chaos_engine.c"] for hook in ENGINE_HOOKS
    ):
        if any(hashlib.sha256(baseline_raw[name]).hexdigest() != digest for name, digest in BASE.items()):
            emit("ERROR", "BASELINE_RUNTIME_HASH_MISMATCH")
            return 2
        emit("RED", "MISSING_RUNTIME_REPLAY_SLICE", (
            "RUNTIME_HEADER", "RUNTIME_MODULE", "NARROW_ENGINE_HOOKS", "REPLAY_STATE_MACHINE",
        ))
        return 1
    if any(not path.is_file() for path in candidates):
        emit("RED", "MISSING_RUNTIME_REPLAY_SLICE", ("RUNTIME_HEADER_OR_MODULE",))
        return 1
    try:
        header = candidates[0].read_text(encoding="utf-8")
        source = candidates[1].read_text(encoding="utf-8")
        protocol = (root / "include/chaos_protocol.h").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        emit("ERROR", "UNREADABLE_RUNTIME_SOURCE")
        return 2

    miss = []
    clean_header = scrub(header)
    clean_source = scrub(source)
    combined = clean_header + "\n" + clean_source
    bodies = {name: function_body(source, name) for name in HOOKS}
    for name in HOOKS:
        if not re.search(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*;", clean_header, re.S):
            miss.append("DECLARATION_" + name)
        if not bodies[name]:
            miss.append("DEFINITION_" + name)

    if "chaos_next_use_runtime.o" not in baseline["GNUmakefile"]:
        miss.append("GNUMAKEFILE_RUNTIME_OBJECT")
    engine = baseline["src/chaos_engine.c"]
    engine_clean = scrub(engine)
    if not all(re.search(r"\b" + hook + r"\s*\(", engine_clean) for hook in ENGINE_HOOKS):
        miss.append("NARROW_ENGINE_HOOKS")
    if any(function_body(engine, hook) for hook in HOOKS):
        miss.append("FORBIDDEN_ENGINE_RUNTIME_IMPLEMENTATION")

    for label, expected in (("slot_w", W_STATES), ("slot_f", F_STATES), ("w_runtime", W_RUNTIME)):
        declarations = enum_members(header, label)
        if len(declarations) != 1 or not normalized_exact(declarations[0], expected):
            miss.append("EXACT_" + label.upper() + "_ENUM")
    w_decl = enum_members(header, "slot_w")
    f_decl = enum_members(header, "slot_f")
    if w_decl and any(member.endswith(("CONSUMED_APPLIED", "CONSUMED_NONREMAPPABLE")) for member in w_decl[0]):
        miss.append("W_ENUM_HAS_F_STATE")
    if f_decl and any(member.endswith("CONSUMED_ARMED") for member in f_decl[0]):
        miss.append("F_ENUM_HAS_W_STATE")

    end_body = bodies["chaos_next_use_end_w"]
    cases = switch_cases(end_body)
    if len(cases) != 7 or not re.search(r"\bswitch\s*\(", end_body):
        miss.append("EXHAUSTIVE_SEVEN_END_W_DISPATCH")
    if not re.search(r"w_runtime[^;{}]*(?:!=|==)[^;{}]*ARMED", end_body):
        miss.append("END_W_NONARMED_NOOP_GUARD")
    for reason, (root_required, outcomes, runtime_after) in END_ROWS.items():
        branch = row_case(cases, reason)
        if not branch:
            miss.append("END_W_ROW_" + reason)
            continue
        if not root_check(branch, root_required):
            miss.append("END_W_ROOT_POLICY_" + reason)
        if not all(outcome in branch for outcome in outcomes) or runtime_after not in branch:
            miss.append("END_W_OUTCOME_STATE_" + reason)
        if reason == "IDENTITY_UNSAFE" and ("W_ENDED_AFTER_WITNESS" in branch or "W_ENDED_NO_WITNESS" in branch):
            miss.append("IDENTITY_UNSAFE_WRONG_OUTCOME")
    if "W_END" in combined and not re.search(r"W_ENDED_(?:AFTER_WITNESS|NO_WITNESS)", combined):
        miss.append("FORBIDDEN_W_END_PLACEHOLDER")
    effect_calls = call_positions(end_body, "effect")
    termination_calls = call_positions(end_body, "termination")
    if not effect_calls or len(termination_calls) != 1 or min(effect_calls) >= termination_calls[0]:
        miss.append("END_W_EFFECT_BEFORE_SOLE_TERMINATION")

    action = bodies["chaos_next_use_on_action"]
    lua_calls = [m.start() for m in re.finditer(r"\bchaos_lua_next_use_on_action\s*\(", action)]
    ordinal_updates = [m.start() for m in re.finditer(r"callback_ordinal\s*(?:\+\+|\+=\s*1)|\+\+\s*\w*callback_ordinal", action)]
    ordinal_records = [m.start() for m in re.finditer(r"(?:intent\w*\.)?callback_ordinal\s*=", action)]
    if len(lua_calls) != 1 or len(ordinal_updates) != 1 or not (
        ordinal_updates[0] < lua_calls[0] and ordinal_records and lua_calls[0] < ordinal_records[-1]
    ):
        miss.append("CHRONOLOGICAL_CALLBACK_ORDINAL_MUTATION")
    invalid_order = (
        r"append\w*intent.*?(?:clear\w*token|token\w*\s*=\s*0).*?CONSUMED_INVALID.*?"
        r"chaos_next_use_end_w\s*\([^)]*INVALID_CALLBACK[^)]*\).*?append\w*termination.*?"
        r"(?:CONTINUE|continue|ORDINARY|ordinary)"
    )
    if not re.search(invalid_order, action, re.S):
        miss.append("INVALID_CALLBACK_LIVE_BRANCH_ORDER")
    if len(re.findall(r"chaos_next_use_end_w\s*\([^)]*INVALID_CALLBACK", action)) != 1:
        miss.append("INVALID_CALLBACK_SINGLE_END_W")
    take = bodies["chaos_next_use_take_identity_unsafe"]
    mark = bodies["chaos_next_use_mark_identity_unsafe"]
    if not re.search(r"identity_unsafe\s*=\s*1", mark) or not re.search(r"identity_unsafe\s*=\s*0", take):
        miss.append("ONE_SHOT_IDENTITY_LATCH")
    take_call = action.find("chaos_next_use_take_identity_unsafe")
    identity_end = re.search(r"chaos_next_use_end_w\s*\([^)]*IDENTITY_UNSAFE", action)
    if take_call < 0 or not identity_end or take_call > identity_end.start() or (lua_calls and identity_end.start() > lua_calls[0]):
        miss.append("IDENTITY_UNSAFE_LIVE_BRANCH_ORDER")

    private_structs = struct_fields(header, "private_record")
    public_structs = struct_fields(header, "public_record")
    termination_structs = struct_fields(header, "termination")
    if private_structs != [PRIVATE_FIELDS]:
        miss.append("EXACT_PRIVATE_RECORD_FIELDS")
    if public_structs != [PUBLIC_FIELDS]:
        miss.append("EXACT_PUBLIC_W_RECORD_FIELDS")
    if termination_structs != [TERMINATION_FIELDS]:
        miss.append("ROOTLESS_TERMINATION_FIELDS")
    if not re.search(r"next_use_private_v\s*(?:==|=)\s*2\b", combined):
        miss.append("PRIVATE_V2_DISCRIMINATOR")
    if not re.search(r"next_use_public_v\s*(?:==|=)\s*2\b", combined):
        miss.append("PUBLIC_V2_DISCRIMINATOR")
    for kind in PRIVATE_KINDS:
        if not re.search(r"\b(?:CHAOS_\w*_)?" + kind.upper() + r"\b|\b" + kind + r"\b", scrub(header, literals=False)):
            miss.append("PRIVATE_KIND_" + kind.upper())
    if not re.search(r"family\s*(?:==|=)\s*[^;\n]*(?:\bW\b|\w*_W\b)", combined) or not re.search(r"phase\s*(?:==|=)\s*[^;\n]*(?:\bwitnessed\b|\w*_WITNESSED\b)", combined, re.I):
        miss.append("PUBLIC_W_ONLY_DISCRIMINANTS")
    public_blocks = re.findall(r"\bstruct\s+\w*public_record\w*\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*;", combined, re.S | re.I)
    if any(re.search(r"\bslot_f\b", block) for block in public_blocks):
        miss.append("FORBIDDEN_F_PUBLIC_RECORD")
    if re.search(r"\b\w*(?:public|witness)\w*\s*\.\s*family\s*=\s*[^;]*(?:\bF\b|\w*_F\b)", combined, re.I):
        miss.append("FORBIDDEN_F_PUBLIC_RECORD")

    protocol_clean = scrub(protocol, literals=False)
    operation = re.findall(r"\bCHAOS_OBS_OP_WHISTLE_ATTENTION\s*=\s*(\d+)\b", protocol_clean)
    fact = re.findall(r"\bCHAOS_OBS_FACT_ATTENTION\s*=\s*(\d+)\b", protocol_clean)
    if operation != ["3"] or fact != ["10"]:
        miss.append("EXACT_OPERATION3_FACT10_CONSTANTS")
    if len(re.findall(r'"whistle_attention"', protocol)) != 1 or len(re.findall(r'"attention"', protocol)) != 1:
        miss.append("EXACT_OPERATION3_FACT10_WIRE_NAMES")

    manifest = bodies["chaos_next_use_on_manifestation"]
    triple = (
        re.search(r"root\s*(?:==|!=)\s*\w*root", manifest)
        and re.search(r"notice_seq\s*(?:==|!=)\s*\w*notice_seq", manifest)
        and re.search(r"end_seq\s*(?:==|!=)\s*\w*end_seq", manifest)
        and re.search(r"root\s*<\s*\w*notice_seq\s*&&\s*\w*notice_seq\s*<\s*\w*end_seq", manifest)
    )
    if not triple or "W_WITNESSED" not in manifest:
        miss.append("DEDICATED_ROOT_TRIPLE_TO_W_WITNESS")
    if not re.search(r"(?:effect\w*\.)?root\s*=\s*(?:intent\w*\.)?root", action):
        miss.append("INTENT_EFFECT_SAME_ROOT")

    replay = bodies["chaos_next_use_replay_record"]
    if not replay or not guarded_replay(replay):
        miss.append("REPLAY_CONJUNCTION_GUARDS_BEFORE_MUTATION")
    if replay and "BLOCKED_REPLAY" not in replay:
        miss.append("REPLAY_MISMATCH_BLOCKS")
    terminal_mutation = re.search(r"(?:->|\.)\s*(?:slot_[wf]|w_runtime|state|seq)\s*=", source)
    if "TERMINATED" not in replay or not re.search(r"(?:if|switch)[\s\S]*TERMINATED[\s\S]*(?:return|BLOCKED_REPLAY)", replay):
        miss.append("REPLAY_TERMINAL_PRESERVATION")
    if terminal_mutation and not re.search(r"if\s*\([^)]*(?:TERMINATED|terminal)[^)]*\)[\s\S]{0,300}(?:return|BLOCKED_REPLAY)", replay, re.I):
        miss.append("NO_POST_TERMINAL_MUTATION_GUARD")

    forbidden = {
        "FORBIDDEN_RUNTIME_RNG": r"\b(?:rn2|rnd|rn1|rnl|random_monster|what_mon)\s*\(",
        "FORBIDDEN_NATIVE_MONSTER_OR_GLYPH": r"\b(?:struct\s+monst|glyph_at|tty_print_glyph|show_glyph)\b",
        "FORBIDDEN_ROOT_IMPLEMENTATION": r"\bchaos_observation_(?:begin_exclusive|finish)\s*\(",
        "FORBIDDEN_SAVE_BONES_OWNERSHIP": r"\b(?:dosave|savegamestate|savelev|bones|restgamestate)\s*\(",
        "FORBIDDEN_CALLBACK_RETRY_OR_ROLLBACK": r"\b(?:retry|rollback|refund|retarget|normalize)\b",
        "FORBIDDEN_PRIVATE_CONTINUITY": r"\bprior_signature\b",
    }
    for code, pattern in forbidden.items():
        if re.search(pattern, clean_source, re.I):
            miss.append(code)
    if manifest and any(token in manifest for token in (
        "chaos_observation_begin_exclusive", "chaos_observation_finish", "lua", "glyph", "struct monst",
    )):
        miss.append("MANIFESTATION_CONSUMER_ONLY")

    if miss:
        emit("RED", "MISSING_RUNTIME_REPLAY_SLICE", tuple(dict.fromkeys(miss)))
        return 1
    emit("GREEN", "RUNTIME_REPLAY_SLICE_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("ERROR", "CHECKER_ERROR_" + type(exc).__name__.upper())
        sys.exit(2)
