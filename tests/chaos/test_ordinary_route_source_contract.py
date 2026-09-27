#!/usr/bin/env python3
"""Closed AST/source contract for R-ROUTE-ADAPTER; never imports it."""
import argparse
import ast
import json
import sys
from pathlib import Path

DEFS = (
    "decode_public_snapshot",
    "validate_start_receipt",
    "next_public_route_action",
    "validate_frozen_continuation",
    "check_route_receipt",
)
OPTIONS = (
    "name:ChaosReview,role:Brd,race:human,gender:male,align:neutral,"
    "pettype:dog,windowtype:tty,!news,!legacy,time,!splash_screen,"
    "!perm_invent,!autopickup"
)
EXPECTED_RULES = {
    "R-01-native-start-identity": {
        "condition": "native_start_identity",
        "action": ("STOP",),
        "limit": ("Brd", "Bard", "human", "male", "neutral", "dog"),
    },
    "R-02-options-and-environment": {
        "condition": "fixed_options_environment",
        "action": ("STOP",),
        "limit": (
            OPTIONS,
            (24, 80),
            (("PATH", "/usr/bin:/bin"), ("TERM", "xterm"),
             ("TZ", "UTC"), ("LC_ALL", "C")),
            ("isolated_HOME", "isolated_TMPDIR", "empty_MAIL",
             "observations_on", "echoes_off", "empty_mailbox", "no_director"),
        ),
    },
    "R-03-initial-random-control": {
        "condition": "initial_random_control",
        "action": ("STOP",),
        "limit": "initial-srandom-zero/pass-through-reseed-v1",
    },
    "R-04-door-open-once": {
        "condition": "ordinary_open_attempts_per_visible_closed_door",
        "action": ("STOP", "ACTION"),
        "limit": 1,
    },
    "R-05-frontier-before-door": {
        "condition": "walkable_frontier_exhausted_before_door",
        "action": ("STOP", "ACTION"),
        "limit": ("k", "l", "j", "h", "u", "n", "b", "y"),
    },
    "R-06-first-fountain-only": {
        "condition": "first_discovered_fountain_frozen",
        "action": ("STOP", "ACTION"),
        "limit": "row,column ascending",
    },
    "R-07-natural-refresh-by-third": {
        "condition": "delivered_natural_water_refreshed_by_drink",
        "action": ("STOP",),
        "limit": 3,
    },
    "R-08-four-drink-total-cap": {
        "condition": "confirmed_affirmative_drinks_prefix_and_continuation",
        "action": ("STOP", "ACTION"),
        "limit": 4,
    },
    "R-09-absolute-move-ceiling": {
        "condition": "absolute_native_moves_before_dispatch",
        "action": ("STOP",),
        "limit": 300,
    },
    "R-10-public-stop-policy": {
        "condition": "all_public_safety_state_known_and_safe",
        "action": ("STOP",),
        "limit": (
            "hp", "hunger", "status", "threat", "pet", "tool",
            "fountain", "level", "input", "vision",
        ),
    },
    "R-11-no-rescue-or-search": {
        "condition": "single_prefix_no_rescue_or_search",
        "action": ("STOP",),
        "limit": (
            "seed_search", "hidden_lookahead", "wizard_rescue", "restore",
            "route_widening", "substitute_tool", "substitute_pet",
            "substitute_fountain", "forced_outcome", "ordinary_singing",
            "favorable_run_replacement",
        ),
    },
    "R-12-continuation-and-matched-replays": {
        "condition": "qualified_frozen_continuation_and_matched_replays",
        "action": ("STOP", "ACTION"),
        "limit": ("on", "passive_off_empty", "exact_on_replay", 3),
    },
}
RULE_OWNERS = {
    "R-01-native-start-identity": ("validate_start_receipt",),
    "R-02-options-and-environment": ("validate_start_receipt",),
    "R-03-initial-random-control": ("validate_start_receipt",),
    "R-04-door-open-once": ("next_public_route_action",),
    "R-05-frontier-before-door": ("next_public_route_action",),
    "R-06-first-fountain-only": ("next_public_route_action",),
    "R-07-natural-refresh-by-third":
        ("next_public_route_action", "check_route_receipt"),
    "R-08-four-drink-total-cap":
        ("next_public_route_action", "validate_frozen_continuation",
         "check_route_receipt"),
    "R-09-absolute-move-ceiling":
        ("next_public_route_action", "validate_frozen_continuation",
         "check_route_receipt"),
    "R-10-public-stop-policy":
        ("decode_public_snapshot", "next_public_route_action",
         "validate_frozen_continuation"),
    "R-11-no-rescue-or-search":
        ("validate_start_receipt", "next_public_route_action",
         "validate_frozen_continuation"),
    "R-12-continuation-and-matched-replays":
        ("validate_frozen_continuation", "check_route_receipt"),
}
SAFE_FROM = {
    "typing": {"Any", "Final", "Mapping", "Sequence"},
    "collections.abc": {"Mapping", "Sequence"},
}
PURE_CALLS = {
    "all", "any", "bool", "bytes", "dict", "enumerate", "float", "int",
    "isinstance", "len", "list", "max", "min", "range", "reversed",
    "sorted", "str", "sum", "tuple", "zip",
} | set(DEFS)
PURE_METHODS = {
    "casefold", "count", "decode", "encode", "endswith", "get", "hex",
    "index", "isalnum", "isalpha", "isascii", "isdecimal", "isdigit",
    "islower", "isnumeric", "isspace", "isupper", "items", "keys",
    "lower", "lstrip", "partition", "removeprefix", "removesuffix",
    "replace", "rpartition", "rsplit", "rstrip", "split", "startswith",
    "strip", "upper", "values",
}
MUTATORS = {
    "add", "append", "clear", "discard", "extend", "insert", "pop",
    "popitem", "remove", "reverse", "setdefault", "sort", "update",
}
FORBIDDEN_NAMES = {
    "Game", "__import__", "breakpoint", "compile", "delattr", "dir",
    "eval", "exec", "getattr", "globals", "help", "input", "locals",
    "memoryview", "open", "random", "setattr", "vars",
}
FORBIDDEN_NODES = (
    ast.AsyncFunctionDef, ast.Await, ast.ClassDef, ast.Delete, ast.Global,
    ast.Lambda, ast.Nonlocal, ast.Raise, ast.Try, ast.While, ast.With,
    ast.AsyncWith, ast.Yield, ast.YieldFrom,
)
ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Constant, ast.ImportFrom, ast.alias,
    ast.AnnAssign, ast.Assign, ast.AugAssign, ast.FunctionDef, ast.arguments,
    ast.arg, ast.Return, ast.If, ast.For, ast.Break, ast.Continue, ast.Pass,
    ast.Name, ast.Load, ast.Store, ast.Subscript, ast.Slice, ast.Dict, ast.List,
    ast.Tuple, ast.Call, ast.keyword, ast.Attribute, ast.BoolOp, ast.BinOp,
    ast.UnaryOp, ast.Compare, ast.IfExp, ast.ListComp, ast.DictComp,
    ast.GeneratorExp, ast.comprehension, ast.And, ast.Or, ast.Add, ast.Sub,
    ast.Mult, ast.FloorDiv, ast.Mod, ast.Not, ast.UAdd, ast.USub, ast.Eq,
    ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In,
    ast.NotIn,
)


def emit(status, code, missing=()):
    print(json.dumps({"checker": "R-ROUTE-ADAPTER", "code": code,
                      "missing": list(missing),
                      "scope": "source_completeness_only_not_semantic_acceptance",
                      "status": status}, sort_keys=True,
                     separators=(",", ":")))


def root_name(node):
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def rule_access(node):
    while isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and node.value.id == "RULES":
            value = node.slice
            return value.value if isinstance(value, ast.Constant) else None
        node = node.value
    return None


def field_accesses(node, rule_id):
    fields = set()
    for part in ast.walk(node):
        if not isinstance(part, ast.Subscript):
            continue
        key = part.slice
        if (isinstance(key, ast.Constant) and key.value in
                {"condition", "action", "limit"} and
                rule_access(part.value) == rule_id):
            fields.add(key.value)
    return fields


def typed_results(statements):
    results = []
    for statement in statements:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
                continue
            values = {}
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    values[key.value] = value
            kind = values.get("kind")
            if not (isinstance(kind, ast.Constant) and kind.value in {"STOP", "ACTION"}):
                continue
            detail = "code" if kind.value == "STOP" else "action"
            if detail in values and isinstance(values[detail], ast.Constant) and isinstance(values[detail].value, str):
                results.append(kind.value)
    return results


def rule_bindings(function):
    bound = {}
    arguments = {arg.arg for arg in (function.args.posonlyargs + function.args.args +
                                      function.args.kwonlyargs)}
    for node in ast.walk(function):
        if not isinstance(node, ast.If):
            continue
        names = {part.id for part in ast.walk(node.test) if isinstance(part, ast.Name)}
        for part in ast.walk(node.test):
            rule_id = rule_access(part) if isinstance(part, ast.Subscript) else None
            if rule_id not in EXPECTED_RULES:
                continue
            fields = field_accesses(node.test, rule_id)
            outcomes = typed_results(node.body) + typed_results(node.orelse)
            if {"condition", "limit"} <= fields and names & arguments:
                allowed = set(EXPECTED_RULES[rule_id]["action"])
                if any(outcome in allowed for outcome in outcomes):
                    bound[rule_id] = True
    return bound


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    root = Path(parser.parse_args().root)
    if not root.is_dir():
        emit("ERROR", "INVALID_ROOT")
        return 2
    path = root / "chaos/ordinary_route.py"
    if not path.exists():
        emit("RED", "MISSING_ROUTE_ADAPTER_SLICE", ("chaos/ordinary_route.py",))
        return 1
    if not path.is_file():
        emit("ERROR", "INVALID_ROUTE_ADAPTER_PATH")
        return 2
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename="ordinary_route.py")
    except (OSError, UnicodeError, SyntaxError):
        emit("ERROR", "INVALID_ROUTE_ADAPTER_SOURCE")
        return 2

    missing = []
    top_functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    all_functions = [node for node in ast.walk(tree)
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if tuple(node.name for node in top_functions) != DEFS or len(all_functions) != 5:
        missing.append("EXACT_FIVE_REQUIRED_DEFINITIONS")

    rules_nodes = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Import):
            missing.append("IMPORT_OUTSIDE_FIXED_PURE_ALLOWLIST")
        elif isinstance(node, ast.ImportFrom):
            names = {alias.name for alias in node.names}
            if node.level or node.module not in SAFE_FROM or not names <= SAFE_FROM[node.module] or any(alias.asname for alias in node.names):
                missing.append("IMPORT_OUTSIDE_FIXED_PURE_ALLOWLIST")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "RULES":
            if not (isinstance(node.annotation, ast.Name) and node.annotation.id == "Final"):
                missing.append("RULES_NOT_FINAL_LITERAL")
            rules_nodes.append(node.value)
        elif isinstance(node, ast.FunctionDef):
            if node.decorator_list:
                missing.append("DECORATED_DEFINITION")
            annotations = ([arg.annotation for arg in
                            (node.args.posonlyargs + node.args.args + node.args.kwonlyargs)
                            if arg.annotation is not None] +
                           ([node.args.vararg.annotation] if node.args.vararg and node.args.vararg.annotation else []) +
                           ([node.args.kwarg.annotation] if node.args.kwarg and node.args.kwarg.annotation else []) +
                           ([node.returns] if node.returns is not None else []))
            if any(isinstance(part, ast.Call) for annotation in annotations
                   for part in ast.walk(annotation)):
                missing.append("TOP_LEVEL_ANNOTATION_CALL")
            defaults = node.args.defaults + [value for value in node.args.kw_defaults
                                             if value is not None]
            try:
                for value in defaults:
                    ast.literal_eval(value)
            except (ValueError, TypeError):
                missing.append("NONLITERAL_DEFINITION_DEFAULT")
        else:
            missing.append("TOP_LEVEL_CALL_OR_SIDE_EFFECT")
    if len(rules_nodes) != 1:
        missing.append("EXACT_RULES_TABLE")
    else:
        try:
            rules_value = ast.literal_eval(rules_nodes[0])
        except (ValueError, TypeError):
            rules_value = None
        if rules_value != EXPECTED_RULES:
            missing.append("EXACT_RULES_TABLE")

    if any(not isinstance(node, ALLOWED_NODES) for node in ast.walk(tree)):
        missing.append("NODE_OUTSIDE_CLOSED_PURE_GRAMMAR")
    if any(isinstance(node, FORBIDDEN_NODES) for node in ast.walk(tree)):
        missing.append("FORBIDDEN_CONTROL_OR_STATE_NODE")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or "__" in node.id):
            missing.append("DYNAMIC_IMPORT_EVAL_REFLECTION_OR_DUNDER")
        if isinstance(node, ast.Attribute):
            if "__" in node.attr or node.attr not in PURE_METHODS:
                missing.append("NON_ALLOWLISTED_ATTRIBUTE")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in PURE_CALLS:
                    missing.append("NON_ALLOWLISTED_CALL")
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in PURE_METHODS or node.func.attr in MUTATORS:
                    missing.append("NON_ALLOWLISTED_CALL")
            else:
                missing.append("NON_ALLOWLISTED_CALL")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, (ast.Subscript, ast.Attribute)):
                    missing.append("CONTAINER_OR_ATTRIBUTE_MUTATION")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in MUTATORS:
            missing.append("CONTAINER_MUTATION")

    for function in top_functions:
        args = {arg.arg for arg in (function.args.posonlyargs + function.args.args +
                                     function.args.kwonlyargs)}
        if args & PURE_CALLS:
            missing.append("CALLABLE_ALLOWLIST_SHADOWED_BY_ARGUMENT")
        for node in ast.walk(function):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(root_name(target) in args for target in targets):
                    missing.append("ARGUMENT_MUTATION_OR_REBIND")
                if any(root_name(target) in PURE_CALLS for target in targets):
                    missing.append("CALLABLE_ALLOWLIST_SHADOWED_BY_LOCAL")
            if isinstance(node, ast.For) and root_name(node.target) in args:
                missing.append("ARGUMENT_MUTATION_OR_REBIND")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in args):
                missing.append("CALL_THROUGH_ARGUMENT")
        bindings = rule_bindings(function)
        for rule_id in bindings:
            if function.name not in RULE_OWNERS[rule_id]:
                missing.append("RULE_BOUND_TO_WRONG_FUNCTION:" + rule_id)

    bindings_by_rule = {rule_id: [] for rule_id in EXPECTED_RULES}
    for function in top_functions:
        for rule_id in rule_bindings(function):
            bindings_by_rule[rule_id].append(function.name)
    for rule_id, owners in bindings_by_rule.items():
        if not owners:
            missing.append("UNBOUND_RULE:" + rule_id)

    if missing:
        emit("RED", "MISSING_ROUTE_ADAPTER_SLICE", tuple(dict.fromkeys(missing)))
        return 1
    emit("GREEN", "ROUTE_ADAPTER_SLICE_COMPLETE")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        emit("ERROR", "CHECKER_ERROR_" + type(exc).__name__.upper())
        sys.exit(2)
