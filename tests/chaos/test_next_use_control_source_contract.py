#!/usr/bin/env python3
"""Read/AST/JSON-only C-CONTROL-SOURCE structural gate; candidates are never run."""
import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path("/home/hermes/.local/share/nyarlathack/feature-planning/pilot22-25/r1-control-candidate/control")
CORE = (
    "ordinary_control.c", "control_probe.c", "libc_api_probe.c", "control_observer.c",
    "control_verify.py", "certificate.schema.json", "launch-manifest.json",
    "build-manifest.json", "symbol-transform-manifest.json",
)
NEG = tuple("fixtures/NEG%02d.json" % number for number in range(1, 15))
MANIFEST_CANDIDATES = tuple(name for name in CORE if name != "launch-manifest.json") + NEG
SCENARIOS = (
    "NATIVE", "API_R", "API_MIX", "API_SR_SRAND", "API_SRAND_R",
    "API_SRAND_RAND", "API_SRAND_MIX", "CLOCK",
)
NEG_REASONS = {
    "NEG01": "PRELOAD_MISSING",
    "NEG02": "PRELOAD_WRONG",
    "NEG03": "INITIAL_EFFECTIVE_NOT_ZERO",
    "NEG04": "UNRECOGNIZED_PREINIT_SEED",
    "NEG05": "RESEED_NOT_PASSTHROUGH",
    "NEG06": "CLOCK_CHANGED",
    "NEG07": "ENTROPY_CONSUMPTION_CHANGED",
    "NEG08": "NATIVE_RESEED_SUPPRESSED",
    "NEG09": "SIGNED_MODULO_CHANGED",
    "NEG10": "ABI_MISMATCH",
    "NEG11": "RNG_BUILD_MISMATCH",
    "NEG12": "BASELINE_HASH_MISMATCH",
    "NEG13": "REQUESTED_EFFECTIVE_CONFLATED",
    "NEG14": "UNSUPPORTED_STATE_INDEPENDENCE",
}
NEG_PATHS = {
    "NEG01": r"(?:environment\.)?LD_PRELOAD|preload",
    "NEG02": r"preload.*(?:path|hash|identity)",
    "NEG03": r"(?:initial|first).*effective",
    "NEG04": r"constructor.*srandom|preinit.*seed",
    "NEG05": r"(?:later|reseed).*effective",
    "NEG06": r"time.*(?:return|pointer|value)",
    "NEG07": r"entropy.*(?:words|generated|consumption)",
    "NEG08": r"(?:first_check|native).*reseed",
    "NEG09": r"(?:signed|modulo|period)",
    "NEG10": r"abi.*(?:sizeof_int|int_size)|sizeof.*int",
    "NEG11": r"(?:RANDOM|random_o|rng_build)",
    "NEG12": r"rnd.*(?:hash|sha256)",
    "NEG13": r"engine_computed_zero|requested.*effective",
    "NEG14": r"rand_random_independent|state.*independence",
}
SOURCE_REVISION = "8c6dc48454ac2e29c6d6ac73e62e57ffd32121fe"
OBJECT_HASHES = {
    "rnd.o": "03cbca20fd473d49a4bc75a4b915dcd96374e2c116c62c3f92a9465fe5bbae59",
    "hacklib.o": "6392758217d2ed3796982776776cff0ca395b50caeaa126d4031e3b87292cab8",
    "options.o": "d226d191fcac3ec849e504358fba2a5bb5038df784f097370e69de252bccf26e",
}
EXECUTABLE_HASH = "42f5e860105d643c58cbc8c86e2c194b3b4a243960057a93df2ca0c5e8721bda"
CONTROL = {
    "mode": "initial-srandom-zero/pass-through-reseed-v1",
    "first_native_initialization_srandom_effective": 0,
    "later_srandom": "requested_unchanged",
    "every_srand_effective": 1234567,
    "time": 1700000000,
    "entropy_initial_uint32": 987654321,
    "entropy_words_generated_per_open": 2,
    "entropy_buffer_bytes": 8,
    "xorshift_shifts": [13, 17, 5],
    "entropy_storage": "host_uint32_bytes",
    "rn2_argument": 1000,
    "rn2_calls": 1421,
    "period_min": -689,
    "period_max": 709,
    "guaranteed_reseeds_min": 3,
    "reseeds_max": 1421,
    "entropy_opens_min": 4,
    "entropy_opens_max": 1422,
    "random_draws": 1421,
    "rand_draws": 0,
}
EXECUTION_RESOURCES = {
    "positive_children": 16,
    "negative_verifier_children": 14,
    "total_children": 30,
    "supervisors": 1,
    "process_groups_concurrent_max": 1,
    "retry_count": 0,
    "descendants_per_child": 0,
    "per_child_cpu_seconds": 2,
    "per_child_wall_seconds": 5,
    "per_child_stream_bytes": 1048576,
    "per_child_observer_private_memory_bytes": 8388608,
    "event_records_max_per_native_child": 20000,
    "aggregate_child_cpu_seconds": 60,
    "aggregate_phase_wall_seconds": 180,
    "aggregate_stream_bytes": 31457280,
    "termination_grace_seconds": 5,
}
PREPARATION_RESOURCES = {
    "compiler_jobs_max": 2,
    "top_level_compile_link_invocations_max": 6,
    "symbol_copy_invocations_max": 2,
    "per_invocation_cpu_seconds": 60,
    "per_invocation_wall_seconds": 60,
    "aggregate_cpu_seconds": 480,
    "aggregate_wall_seconds": 480,
    "aggregate_stream_bytes": 8388608,
    "live_descendants_max": 16,
    "descendant_starts_max": 64,
}
LAUNCH_KEYS = {
    "schema", "status", "source_revision", "scope", "fresh_exec", "no_game",
    "scenario_order", "repeats_per_positive", "positive_children", "negative_children",
    "supervisor", "control", "execution_resources", "preparation_resources", "candidate_files",
}
BUILD_KEYS = {
    "schema", "status", "source_revision", "build_directory", "build_time_local_mk",
    "objects", "retained_executable_sha256", "compile_vectors", "private_link_vector",
    "export_vector", "tool_hashes", "object_count", "preparation_resources",
}
SYMBOL_KEYS = {
    "schema", "status", "source_revision", "symbol_copy_vectors", "symbols", "call_sites",
    "section_comparison", "observer_resolution", "tool_hashes",
}


class Duplicate(ValueError):
    pass


def emit(status, code, missing=(), launch_receipt=None):
    payload = {
        "checker": "C-CONTROL-SOURCE",
        "code": code,
        "missing": list(missing),
        "scope": "source_completeness_only_not_semantic_acceptance",
        "status": status,
    }
    if launch_receipt is not None:
        payload["external_launch_manifest"] = launch_receipt
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Duplicate(key)
        result[key] = value
    return result


def strip_c(text, literals=True):
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
    clean = strip_c(text, literals=False)
    for match in re.finditer(r"\b" + re.escape(name) + r"\s*\(", clean):
        opening = clean.find("(", match.start())
        _, after = balanced(clean, opening, "(", ")")
        if after < 0:
            continue
        suffix = clean[after:]
        offset = len(suffix) - len(suffix.lstrip())
        if suffix[offset:].startswith(";"):
            continue
        brace = clean.find("{", after, after + 800)
        if brace >= 0:
            block, _ = balanced(clean, brace, "{", "}")
            if block:
                return block
    return ""


def exact_keys(value, expected):
    return isinstance(value, dict) and set(value) == expected


def string_vector(value, minimum=1):
    return isinstance(value, list) and len(value) >= minimum and all(isinstance(item, str) and item for item in value)


def closed_json_schema(node):
    if not isinstance(node, dict) or node.get("$schema") is None:
        return False
    stack = [node]
    while stack:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        if current.get("type") == "object":
            properties = current.get("properties")
            required = current.get("required")
            if not isinstance(properties, dict) or current.get("additionalProperties") is not False:
                return False
            if not isinstance(required, list) or set(required) != set(properties) or len(required) != len(properties):
                return False
            stack.extend(properties.values())
        for key in ("items", "oneOf", "anyOf", "allOf", "$defs", "definitions"):
            child = current.get(key)
            if isinstance(child, dict):
                stack.extend(child.values() if key in ("$defs", "definitions") else [child])
            elif isinstance(child, list):
                stack.extend(child)
    return True


def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key in sorted(value):
            path = prefix + "." + key if prefix else key
            result.update(flatten(value[key], path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.update(flatten(item, "%s[%d]" % (prefix, index)))
    else:
        result[prefix] = value
    return result


def one_declared_fault(fixture, ident):
    expected_keys = {"id", "kind", "positive", "candidate", "fault_path", "expected_rejection"}
    if not exact_keys(fixture, expected_keys):
        return False
    if fixture["id"] != ident or fixture["kind"] != "verifier_only_single_fault":
        return False
    if fixture["expected_rejection"] != NEG_REASONS[ident]:
        return False
    if not isinstance(fixture["positive"], dict) or not isinstance(fixture["candidate"], dict):
        return False
    positive = flatten(fixture["positive"])
    candidate = flatten(fixture["candidate"])
    differences = sorted(set(positive) ^ set(candidate))
    differences.extend(sorted(key for key in set(positive) & set(candidate) if positive[key] != candidate[key]))
    differences = sorted(set(differences))
    return (
        len(differences) == 1
        and fixture["fault_path"] == differences[0]
        and re.search(NEG_PATHS[ident], fixture["fault_path"], re.I) is not None
    )


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + "." + node.attr if base else node.attr
    return ""


def verifier_ast_ok(tree):
    allowed_imports = {"argparse", "collections", "hashlib", "json", "pathlib", "re", "sys", "typing"}
    forbidden_names = {
        "eval", "exec", "compile", "__import__", "breakpoint", "getattr", "setattr", "delattr",
        "hasattr", "globals", "locals", "vars", "dir", "memoryview", "input", "open", "help",
        "subprocess", "ctypes", "cffi", "importlib", "marshal", "pickle", "shelve", "os", "socket",
        "signal", "multiprocessing", "resource", "runpy",
    }
    allowed_builtins = {
        "all", "any", "bool", "bytes", "dict", "enumerate", "filter", "frozenset", "int",
        "isinstance", "len", "list", "map", "max", "min", "next", "print", "range", "reversed",
        "set", "sorted", "str", "sum", "tuple", "zip", "Path",
    }
    allowed_calls = {
        "argparse.ArgumentParser", "hashlib.sha256", "json.dump", "json.dumps", "json.load", "json.loads",
        "re.compile", "re.fullmatch", "re.match", "re.search", "sys.exit",
    }
    allowed_methods = {
        "add", "append", "decode", "encode", "endswith", "extend", "get", "hexdigest", "is_dir",
        "is_file", "items", "join", "keys", "lower", "read_bytes", "read_text", "replace", "setdefault",
        "sort", "split", "startswith", "strip", "update", "upper", "values",
    }
    defined = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not defined or not any(name.startswith("verify") for name in defined):
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom, ast.ClassDef)):
            return False
        if isinstance(node, ast.Import):
            if any(alias.name not in allowed_imports for alias in node.names):
                return False
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") not in allowed_imports or node.level:
                return False
        if isinstance(node, ast.Name) and (node.id in forbidden_names or node.id.startswith("__")):
            return False
        if isinstance(node, ast.Attribute) and (node.attr.startswith("__") or node.attr in forbidden_names):
            return False
        if isinstance(node, ast.Call):
            name = dotted(node.func)
            if isinstance(node.func, ast.Name):
                if name not in allowed_builtins and name not in defined:
                    return False
            elif isinstance(node.func, ast.Attribute):
                if name not in allowed_calls and node.func.attr not in allowed_methods:
                    return False
            else:
                return False
    return True


def typed_manifest_checks(launch, build, symbols):
    failures = []
    if not exact_keys(launch, LAUNCH_KEYS):
        failures.append("CLOSED_LAUNCH_MANIFEST")
        return failures
    if not exact_keys(build, BUILD_KEYS):
        failures.append("CLOSED_BUILD_MANIFEST")
        return failures
    if not exact_keys(symbols, SYMBOL_KEYS):
        failures.append("CLOSED_SYMBOL_MANIFEST")
        return failures
    if any(doc.get("source_revision") != SOURCE_REVISION for doc in (launch, build, symbols)):
        failures.append("PINNED_SOURCE_REVISION")
    if launch.get("fresh_exec") is not True or launch.get("no_game") is not True:
        failures.append("FRESH_EXEC_NO_GAME")
    if launch.get("scenario_order") != list(SCENARIOS) or launch.get("repeats_per_positive") != 2:
        failures.append("EXACT_SCENARIO_ORDER_AND_REPEATS")
    expected_positive = [
        {"scenario": scenario, "repeat": repeat, "fresh_exec": True, "retry": 0, "descendants": 0}
        for scenario in SCENARIOS for repeat in (1, 2)
    ]
    if launch.get("positive_children") != expected_positive:
        failures.append("EXACT_SIXTEEN_POSITIVE_CHILDREN")
    expected_negative = [
        {"id": ident, "kind": "verifier_only", "fresh_exec": True, "retry": 0, "descendants": 0}
        for ident in NEG_REASONS
    ]
    if launch.get("negative_children") != expected_negative:
        failures.append("EXACT_FOURTEEN_VERIFIER_CHILDREN")
    if launch.get("supervisor") != {
        "children": 30, "supervisors": 1, "process_groups_concurrent_max": 1,
        "retry_count": 0, "probe_descendants": 0,
    }:
        failures.append("THIRTY_CHILDREN_ONE_SUPERVISOR_NO_RETRY_DESCENDANTS")
    if launch.get("control") != CONTROL:
        failures.append("EXACT_CONTROL_CONSTANTS_AND_1421_ARITHMETIC")
    execution = launch.get("execution_resources")
    preparation = launch.get("preparation_resources")
    if execution != EXECUTION_RESOURCES:
        failures.append("EXACT_EXECUTION_RESOURCE_CAPS")
    if preparation != PREPARATION_RESOURCES or build.get("preparation_resources") != PREPARATION_RESOURCES:
        failures.append("EXACT_PREPARATION_RESOURCE_CAPS")
    if isinstance(execution, dict):
        arithmetic = (
            execution.get("positive_children") == len(SCENARIOS) * launch.get("repeats_per_positive", -1)
            and execution.get("total_children") == execution.get("positive_children", -1) + execution.get("negative_verifier_children", -1)
            and execution.get("aggregate_child_cpu_seconds") == execution.get("total_children", -1) * execution.get("per_child_cpu_seconds", -1)
            and execution.get("aggregate_stream_bytes") == execution.get("total_children", -1) * execution.get("per_child_stream_bytes", -1)
        )
        if not arithmetic:
            failures.append("RESOURCE_CAP_ARITHMETIC")
    candidate_files = launch.get("candidate_files")
    expected_files = list(MANIFEST_CANDIDATES)
    expected_count = len(CORE) + len(NEG) - 1
    if (not isinstance(candidate_files, list) or len(candidate_files) != expected_count
            or [row.get("path") for row in candidate_files if isinstance(row, dict)] != expected_files):
        failures.append("CANDIDATE_FILE_INVENTORY")
    elif any(set(row) != {"path", "bytes", "sha256"} or not isinstance(row["bytes"], int)
             or row["bytes"] <= 0 or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
             for row in candidate_files):
        failures.append("TYPED_CANDIDATE_FILE_HASHES")

    if build.get("objects") != OBJECT_HASHES or build.get("retained_executable_sha256") != EXECUTABLE_HASH:
        failures.append("RETAINED_OBJECT_EXECUTABLE_PROVENANCE")
    if build.get("build_time_local_mk") != "UNKNOWN" or build.get("object_count") != 145:
        failures.append("LINK_CLOSURE_AND_LOCAL_MK_PROVENANCE")
    compile_vectors = build.get("compile_vectors")
    if not isinstance(compile_vectors, dict) or set(compile_vectors) != {"hacklib.o", "rnd.o"} or not all(
        string_vector(vector) for vector in compile_vectors.values()
    ):
        failures.append("EXACT_TYPED_COMPILE_VECTORS")
    for key in ("private_link_vector", "export_vector"):
        if not string_vector(build.get(key)):
            failures.append("EXACT_TYPED_" + key.upper())
    if not isinstance(build.get("tool_hashes"), dict) or not build["tool_hashes"]:
        failures.append("BUILD_TOOL_HASHES")

    copy_vectors = symbols.get("symbol_copy_vectors")
    if not isinstance(copy_vectors, list) or len(copy_vectors) != 2 or not all(string_vector(item) for item in copy_vectors):
        failures.append("EXACT_TWO_SYMBOL_COPY_VECTORS")
    symbol_rows = symbols.get("symbols")
    call_sites = symbols.get("call_sites")
    if not isinstance(symbol_rows, list) or not symbol_rows or any(
        not exact_keys(row, {"module", "name", "size", "version", "exported"})
        or not isinstance(row["size"], int) or row["size"] <= 0 for row in symbol_rows
    ):
        failures.append("TYPED_SYMBOL_SIZE_VECTOR")
    if not isinstance(call_sites, list) or not call_sites or any(
        not exact_keys(row, {"caller_module_sha256", "caller_symbol", "callee", "module_offset"})
        or not re.fullmatch(r"[0-9a-f]{64}", row["caller_module_sha256"])
        or not isinstance(row["module_offset"], int) or row["module_offset"] < 0 for row in call_sites
    ):
        failures.append("TYPED_CALLSITE_PROVENANCE_VECTOR")
    if symbols.get("section_comparison") != {
        "compared": ["allocatable_sections", ".text", "relocations"],
        "before_after_equal": True,
        "allowed_changes": ["symbol_table"],
    }:
        failures.append("SECTION_TEXT_RELOCATION_EQUALITY_VECTOR")
    resolution = symbols.get("observer_resolution")
    if not exact_keys(resolution, {"providers", "versions", "build_ids", "constructor_side_effects", "resolution_side_effects"}):
        failures.append("OBSERVER_PROVIDER_RESOLUTION_VECTOR")
    elif resolution["constructor_side_effects"] != "none" or resolution["resolution_side_effects"] != "none":
        failures.append("OBSERVER_RESOLUTION_SIDE_EFFECT_CLOSURE")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    root = Path(parser.parse_args().root)
    if not root.is_dir():
        emit("ERROR", "INVALID_ROOT")
        return 2
    names = CORE + NEG
    if not BASE.is_dir() or any(not (BASE / name).is_file() for name in names):
        missing = [name for name in names if not (BASE / name).is_file()]
        emit("RED", "MISSING_CONTROL_SOURCE_CANDIDATE", missing or (str(BASE),))
        return 1
    try:
        raw = {name: (BASE / name).read_bytes() for name in names}
        launch_receipt = {
            "path": "launch-manifest.json",
            "bytes": len(raw["launch-manifest.json"]),
            "sha256": hashlib.sha256(raw["launch-manifest.json"]).hexdigest(),
        }
        text = {name: value.decode("utf-8") for name, value in raw.items()}
        tree = ast.parse(text["control_verify.py"], filename="control_verify.py")
        documents = {
            name: json.loads(text[name], object_pairs_hook=pairs)
            for name in CORE if name.endswith(".json")
        }
        fixtures = {name: json.loads(text[name], object_pairs_hook=pairs) for name in NEG}
    except (OSError, UnicodeError, SyntaxError, json.JSONDecodeError, Duplicate):
        emit("ERROR", "INVALID_CONTROL_SOURCE_CANDIDATE")
        return 2

    miss = []
    schema = documents["certificate.schema.json"]
    launch = documents["launch-manifest.json"]
    build = documents["build-manifest.json"]
    symbols = documents["symbol-transform-manifest.json"]
    if not closed_json_schema(schema):
        miss.append("RECURSIVELY_CLOSED_CERTIFICATE_SCHEMA")
    miss.extend(typed_manifest_checks(launch, build, symbols))

    if not verifier_ast_ok(tree):
        miss.append("STRICT_READ_ONLY_VERIFIER_AST_ALLOWLIST")
    verifier_text = text["control_verify.py"]
    if not all(reason in verifier_text for reason in NEG_REASONS.values()):
        miss.append("VERIFIER_EXACT_REJECTION_REASONS")
    if re.search(r"\b(?:eval|exec|compile|__import__|getattr|setattr|hasattr|globals|locals|vars)\s*\(", verifier_text):
        miss.append("VERIFIER_DYNAMIC_OR_REFLECTION_CAPABILITY")

    for index, name in enumerate(NEG, 1):
        ident = "NEG%02d" % index
        if not one_declared_fault(fixtures[name], ident):
            miss.append("EXACT_SINGLE_FAULT_" + ident)
    if len({hashlib.sha256(raw[name]).hexdigest() for name in NEG}) != 14:
        miss.append("FOURTEEN_DISTINCT_NEGATIVE_FIXTURE_BYTES")

    ordinary = text["ordinary_control.c"]
    probe = text["control_probe.c"]
    api_probe = text["libc_api_probe.c"]
    observer = text["control_observer.c"]
    ordinary_clean = strip_c(ordinary)
    probe_main = function_body(probe, "main")
    api_main = function_body(api_probe, "main")
    observer_bodies = {
        name: function_body(observer, name)
        for name in ("control_observer_init", "control_observer_record", "control_observer_finish")
    }
    if not probe_main:
        miss.append("NAMED_NATIVE_PROBE_MAIN")
    else:
        if len(re.findall(r"\bsetrandom\s*\(", probe_main)) != 1:
            miss.append("ACTUAL_SET_RANDOM_ONCE")
        if len(re.findall(r"\brn2\s*\(\s*1000\s*\)", probe_main)) != 1:
            miss.append("ACTUAL_RN2_1000_LOOP_BODY")
        if not re.search(r"\bfor\s*\([^;]*;[^;]*(?:<\s*1421|<=\s*1420)[^;]*;", probe_main):
            miss.append("EXACT_1421_NATIVE_CALL_LOOP")
        if re.search(r"\b(?:initoptions|newgame|moveloop|mklev|original_game_main|main_game)\s*\(", probe_main):
            miss.append("FORBIDDEN_GAME_ENTRY")
    if not api_main or re.search(r"\b(?:setrandom|rn2|initoptions|newgame|moveloop|mklev)\s*\(", api_main):
        miss.append("LIBC_API_PROBE_ISOLATION")

    for name in ("time", "fopen", "fread", "fclose", "srandom", "srand", "random", "rand"):
        if not function_body(ordinary, name):
            miss.append("CONTROL_INTERPOSER_" + name.upper())
    policy_checks = (
        re.search(r"first\w*.*srandom|srandom\w*.*ordinal", ordinary_clean, re.S),
        re.search(r"effective\w*\s*=\s*0\b", ordinary_clean),
        re.search(r"effective\w*\s*=\s*requested|real_srandom\s*\(\s*requested", ordinary_clean),
        re.search(r"real_srand\s*\(\s*1234567\s*\)", ordinary_clean),
        re.search(r"1700000000", ordinary_clean),
        re.search(r"987654321", ordinary_clean),
        re.search(r"<<\s*13[\s\S]*>>\s*17[\s\S]*<<\s*5", ordinary_clean),
    )
    if not all(policy_checks):
        miss.append("STRUCTURAL_CONTROL_POLICY_CONSTANTS")

    if any(not body for body in observer_bodies.values()):
        miss.append("NAMED_OBSERVER_BODIES")
    observer_clean = strip_c(observer)
    if not re.search(r"\bstatic\b[^;]*\[[ ]*20000[ ]*\]", observer_clean, re.S):
        miss.append("PREALLOCATED_EVENT_RECORDS")
    if not re.search(r"(?:record_count|event_count|next_record)[^;{}]*(?:>=|<)\s*20000", observer_clean):
        miss.append("EVENT_RECORD_BOUND_CHECK")
    if not re.search(r"\bstatic\b[^;]*\[[ ]*(?:1048576|8388608)[ ]*\]", observer_clean, re.S):
        miss.append("PREALLOCATED_SERIALIZATION_OR_PRIVATE_MEMORY")
    observer_measurement = "\n".join(observer_bodies[name] for name in ("control_observer_init", "control_observer_record"))
    forbidden_observer = r"\b(?:malloc|calloc|realloc|free|aligned_alloc|fopen|fdopen|printf|fprintf|sprintf|snprintf|puts|fputs|backtrace|unwind|setstate|initstate|clock|gettimeofday|clock_gettime|nanosleep|sleep|signal|sigaction|raise|fork|vfork|clone|exec\w*|posix_spawn|system|popen|dlopen)\s*\("
    if re.search(forbidden_observer, observer_measurement):
        miss.append("OBSERVER_MEASUREMENT_FORBIDDEN_BEHAVIOR")
    finish = observer_bodies["control_observer_finish"]
    if not re.search(r"measurement_(?:done|complete)|MEASUREMENT_(?:DONE|COMPLETE)", finish) or not re.search(r"\bwrite\s*\(", finish):
        miss.append("DETERMINISTIC_FD_ONLY_AFTER_MEASUREMENT")
    if re.search(r"\b(?:random|rand|srandom|srand)\s*\(", observer_measurement):
        miss.append("OBSERVER_EXTRA_RNG_OR_SEED_CALL")
    if not all(token in observer for token in ("errno", "constructor", "dlsym", "dladdr")):
        miss.append("OBSERVER_ABI_PROVIDER_SURFACE")

    all_c_clean = "\n".join(strip_c(text[name]) for name in CORE if name.endswith(".c"))
    if re.search(r"\b(?:Game|gameplay_support|pty|socket|connect|accept|curl|requests)\b", all_c_clean, re.I):
        miss.append("FORBIDDEN_GAME_OR_NETWORK_SOURCE")
    if re.search(r"\b(?:fork|vfork|clone|exec\w*|posix_spawn|system|popen)\s*\(", all_c_clean):
        miss.append("FORBIDDEN_CHILD_PROCESS_SOURCE")

    manifest_rows = launch.get("candidate_files") if isinstance(launch, dict) else None
    if isinstance(manifest_rows, list):
        recorded = {row.get("path"): row for row in manifest_rows if isinstance(row, dict)}
        for name in MANIFEST_CANDIDATES:
            row = recorded.get(name)
            if row and (row.get("bytes") != len(raw[name]) or row.get("sha256") != hashlib.sha256(raw[name]).hexdigest()):
                miss.append("CANDIDATE_MANIFEST_BYTE_MISMATCH_" + name.replace("/", "_"))

    if miss:
        emit("RED", "INCOMPLETE_CONTROL_SOURCE_CANDIDATE", tuple(dict.fromkeys(miss)), launch_receipt)
        return 1
    emit("GREEN", "CONTROL_SOURCE_CANDIDATE_COMPLETE", launch_receipt=launch_receipt)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("ERROR", "CHECKER_ERROR_" + type(exc).__name__.upper())
        sys.exit(2)
