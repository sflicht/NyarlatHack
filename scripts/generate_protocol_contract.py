#!/usr/bin/env python3
"""Render the reviewed v1 contract; --check is read-only and needs only stdlib."""

import argparse
import difflib
import json
from pathlib import Path
import pprint
import re
import sys

BEGIN = "/* BEGIN GENERATED PROTOCOL CONTRACT */"
END = "/* END GENERATED PROTOCOL CONTRACT */"


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def validate_observations(o):
    def require(ok, why):
        if not ok:
            raise ValueError("observations: " + why)

    def keys(row, fields):
        require(type(row) is dict and set(row) == set(fields.split()), "keys")

    def word(value):
        return type(value) is str and re.fullmatch(r"[a-z][a-z_]{0,30}", value)

    def identities(rows, prefix, first, extra):
        require(type(rows) is list and bool(rows), "rows")
        for i, row in enumerate(rows, first):
            keys(row, "symbol id name " + extra)
            require(type(row["id"]) is int and row["id"] == i, "integer identity")
            require(word(row["name"]), "literal name")
            require(
                type(row["symbol"]) is str
                and re.fullmatch(prefix + r"[A-Z_]{1,31}", row["symbol"]),
                "symbol",
            )
        for field in ("name", "symbol"):
            require(len({r[field] for r in rows}) == len(rows), "unique " + field)

    keys(
        o,
        "format wire_version operation_none fact_none stages channels families facts projection",
    )
    for key, value in (("format", 1), ("wire_version", 4)):
        require(type(o[key]) is int and o[key] == value, key)
    for key, prefix in (
        ("operation_none", "CHAOS_OBS_OP_"),
        ("fact_none", "CHAOS_OBS_FACT_"),
    ):
        require(
            o[key] == dict(symbol=prefix + "NONE", id=0, name="none")
            and type(o[key]["id"]) is int,
            "sentinel",
        )
        keys(o[key], "symbol id name")
    families, facts = o["families"], o["facts"]
    require(type(families) is list and 1 <= len(families) <= 16, "family cap")
    require(type(facts) is list and 1 <= len(facts) <= 64, "fact cap")
    # Check original row containers/keys before indexing for sentinel collisions.
    identities(families, "CHAOS_OBS_OP_", 1, "allow_blocked projection hook_refs")
    identities(facts, "CHAOS_OBS_FACT_", 1, "operation channel implies_blocked")
    identities(
        [o["operation_none"]]
        + [dict(symbol=r["symbol"], id=r["id"], name=r["name"]) for r in families],
        "CHAOS_OBS_OP_",
        0,
        "",
    )
    identities(
        [o["fact_none"]]
        + [dict(symbol=r["symbol"], id=r["id"], name=r["name"]) for r in facts],
        "CHAOS_OBS_FACT_",
        0,
        "",
    )
    identities(o["stages"], "CHAOS_OBS_STAGE_", 0, "phase role")
    require(
        [(r["symbol"], r["id"], r["name"], r["phase"], r["role"]) for r in o["stages"]]
        == [
            ("CHAOS_OBS_STAGE_ENABLED", 0, "enabled", "result", "enable"),
            ("CHAOS_OBS_STAGE_STARTED", 1, "started", "attempt", "start"),
            ("CHAOS_OBS_STAGE_NOTICE", 2, "notice", "result", "notice"),
            ("CHAOS_OBS_STAGE_COMPLETED", 3, "completed", "result", "complete"),
            ("CHAOS_OBS_STAGE_BLOCKED", 4, "blocked", "result", "block"),
        ],
        "stage semantics",
    )
    require(
        o["channels"]
        == [
            dict(name="message", witness="native_tty_rendered"),
            dict(name="map", witness="native_tty_blocking_map_presented"),
        ],
        "channel witnesses",
    )
    p = o["projection"]
    keys(p, "context_version scope lookback_roots count_cap evidence summary_bytes")
    for key, value in (
        ("context_version", 1),
        ("lookback_roots", 32),
        ("count_cap", 3),
        ("summary_bytes", 4096),
    ):
        require(type(p[key]) is int and p[key] == value, "projection bounds")
    require(
        word(p["scope"]) and p["evidence"] == "first_two_latest", "projection policy"
    )
    for row in families:
        require(
            type(row["allow_blocked"]) is bool
            and row["projection"] == "completed_notice_by_operation",
            "family policy",
        )
        require(
            type(row["hook_refs"]) is list and bool(row["hook_refs"]), "hook provenance"
        )
        require(
            len({json.dumps(r, sort_keys=True) for r in row["hook_refs"]})
            == len(row["hook_refs"]),
            "duplicate hook reference",
        )
        for ref in row["hook_refs"]:
            keys(ref, "file symbol role")
            require(
                type(ref["file"]) is str
                and re.fullmatch(
                    r"(?:src|win/tty|tests/chaos)/[a-z_]+\.c", ref["file"]
                ),
                "hook file",
            )
            require(
                type(ref["symbol"]) is str
                and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", ref["symbol"])
                and word(ref["role"]),
                "hook symbol/role",
            )
    for row in facts:
        require(
            type(row["operation"]) is int and 1 <= row["operation"] <= len(families),
            "fact owner",
        )
        require(
            row["channel"] in ("message", "map")
            and type(row["implies_blocked"]) is bool,
            "fact policy",
        )
        require(
            not row["implies_blocked"]
            or families[row["operation"] - 1]["allow_blocked"],
            "blocking fact owner",
        )
    # Names are literal ASCII, max 31 bytes; maximum root is ten digits.
    suffix = (
        ',"observation":{"operation":"%s","stage":"%s","root_seq":2147483647,"fact":"%s"}'
        % ("x" * 31, "x" * 31, "x" * 31)
    )
    require(len(suffix) < 512, "writer suffix cap")


def validate(d):
    def require(ok, why):
        if not ok:
            raise ValueError(why)

    require(
        set(d)
        == set(
            "format legacy cosmetic observations versions limits budget non_effect_spenders request_fields mutations telegraphs ambient_messages results events phases ack_statuses journal_status event_numbers vitals ack_numbers ack_number_bounds reader_policy wire_order".split()
        ),
        "contract keys",
    )
    # SHA256 of canonical sorted compact JSON projected from the original
    # c00029de0ef54bf89dc0d283b8e4f0fc365beb11:chaos/protocol_contract.json.
    # Freeze the COMPLETE introduced subtree, and shared parser metadata which
    # legacy readers still consume. A future change needs explicit versioning,
    # not a blind digest refresh. Tests compare with the actual Git baseline.
    import hashlib

    def fingerprint(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    require(
        fingerprint(d["legacy"])
        == "159623c852ee31a45e89ee64d44a88381f46b08c882a46a543eb8b9fa1b57a39",
        "frozen legacy metadata",
    )
    shared = "limits ack_number_bounds request_fields vitals events phases ack_statuses telegraphs ambient_messages budget non_effect_spenders journal_status".split()
    require(
        fingerprint({k: d[k] for k in shared})
        == "b05ec2a3bccc89c735a2847e1bae007f4291661f96e35c3049c14e639903d493",
        "frozen shared legacy metadata",
    )
    require(type(d["format"]) is int and d["format"] == 1, "unknown contract format")
    for section, keys in {
        "versions": "request event state",
        "limits": "max_int max_counter request_bytes event_input_cap event_detail_characters request_string_buffer admission_turn_headroom",
        "budget": "sanity_min sanity_max base step ceiling",
    }.items():
        require(
            type(d[section]) is dict and set(d[section]) == set(keys.split()),
            f"{section} keys",
        )
    # Formats have handwritten variadic C arguments: changing their order is unsafe.
    require(
        d["wire_order"]
        == {
            "event": "v seq turn safe event phase detail sanity insight budget spent reserved last_id vitals cosmetic".split(),
            "ack_extra": "id status mutation value duration telegraph at cost cosmetic_cost expires".split(),
            "journal_prefix": "v policy turn safe".split(),
        },
        "fixed serializer roles/order",
    )
    require(
        [r["wire"] for r in d["vitals"]] == "hp hp_max power power_max".split(),
        "fixed vitals roles/order",
    )
    require(
        {r["wire"] for r in d["event_numbers"]}
        == set("v seq turn safe sanity insight budget spent reserved last_id".split()),
        "event number roles",
    )
    require(
        set(d["ack_numbers"])
        == set("id value duration telegraph at cost cosmetic_cost expires".split()),
        "ack number roles",
    )
    require(
        type(d["reader_policy"].get("vitals_optional")) is bool, "reader policy type"
    )
    for section in ("versions", "limits", "budget"):
        require(
            all(type(v) is int and v >= 0 for v in d[section].values()),
            f"integer {section}",
        )
    require(
        d["cosmetic"] == dict(limit=3, spacing=50, mask=7, policy=2)
        and all(type(v) is int for v in d["cosmetic"].values()),
        "cosmetic policy",
    )
    require(d["versions"] == dict(request=1, event=3, state=2), "current versions")
    validate_observations(d["observations"])
    limits = d["limits"]
    require(
        limits["max_int"] == 2147483647 and limits["max_counter"] == limits["max_int"],
        "wire integer ABI",
    )
    require(limits["request_string_buffer"] > 1, "string buffer")
    budget = d["budget"]
    require(
        budget["step"] > 0
        and budget["ceiling"]
        == budget["base"]
        + (budget["sanity_max"] - budget["sanity_min"]) // budget["step"],
        "budget ceiling",
    )

    rows = d["non_effect_spenders"]
    require(type(rows) is list and len(rows) == 2, "non-effect spenders")
    for i, (row, name) in enumerate(zip(rows, ("curio", "haunt")), 1):
        require(
            type(row) is dict
            and set(row) == {"name", "id", "cost"}
            and row["name"] == name
            and type(row["id"]) is int
            and row["id"] == i
            and type(row["cost"]) is int
            and 0 < row["cost"] <= budget["ceiling"],
            "non-effect identity/cost",
        )

    def bounds(value):
        require(
            type(value) is list
            and len(value) == 2
            and all(type(n) is int for n in value)
            and -limits["max_int"] <= value[0] <= value[1] <= limits["max_int"],
            "integer bounds",
        )

    def words(values):
        require(
            len(values) == len(set(values))
            and all(type(s) is str and re.fullmatch("[a-z][a-z_]*", s) for s in values),
            "unique literal names",
        )

    for key in ("events", "phases", "ack_statuses", "ack_numbers"):
        words(d[key])
    for key in ("mutations", "results"):
        rows = d[key]
        require(bool(rows), "empty registry")
        words([r["name"] for r in rows])
        require(len({r["symbol"] for r in rows}) == len(rows), "duplicate symbols")
        for i, row in enumerate(rows):
            require(
                type(row["id"]) is int
                and row["id"] == i
                and re.fullmatch("CHAOS_[A-Z_]+", row["symbol"]),
                "enum identity",
            )
    for key, field in (("telegraphs", "id"), ("ambient_messages", "value")):
        for i, row in enumerate(d[key], 1):
            require(
                set(row) == {field, "text"}
                and type(row[field]) is int
                and row[field] == i,
                "message identity",
            )
            require(
                type(row["text"]) is str
                and all(32 <= ord(c) < 127 for c in row["text"]),
                "ASCII message",
            )
    for row in d["mutations"]:
        require(
            set(row)
            == set(
                "symbol id name cost cosmetic_cost value duration telegraph engine_sanity_max director_sanity_max ordinary_food persistent rule".split()
            ),
            "mutation keys",
        )
        for key in ("cost", "cosmetic_cost", "telegraph", "director_sanity_max"):
            require(type(row[key]) is int and 0 <= row[key] <= limits["max_int"], key)
        require(
            row["engine_sanity_max"] is None
            or type(row["engine_sanity_max"]) is int
            and 0 <= row["engine_sanity_max"] <= limits["max_int"],
            "engine sanity",
        )
        require(
            type(row["ordinary_food"]) is bool and type(row["persistent"]) is bool,
            "predicate type",
        )
        require(
            (
                row["name"] == "ambient"
                and row["symbol"] == "CHAOS_AMBIENT"
                and row["id"] == 0
                and row["cost"] == 0
                and row["cosmetic_cost"] == 1
                and row["value"] == [1, 3]
                and len(d["ambient_messages"]) == 3
            )
            or (
                row["name"] != "ambient"
                and 0 < row["cost"] <= budget["ceiling"]
                and row["cosmetic_cost"] == 0
            ),
            "cost",
        )
        require(1 <= row["telegraph"] <= len(d["telegraphs"]), "telegraph reference")
        require(
            len(row["name"]) < limits["request_string_buffer"], "request name length"
        )
        bounds(row["value"])
        bounds(row["duration"])
        require(
            row["value"][0] > 0
            and 0
            <= row["duration"][0]
            <= row["duration"][1]
            <= limits["admission_turn_headroom"],
            "mutation bounds",
        )
        require(row["rule"] in ("none", "halve", "double"), "rule tag")
        require(
            (row["persistent"] and row["duration"][0] > 0 and row["rule"] != "none")
            or (
                not row["persistent"]
                and row["duration"] == [0, 0]
                and row["rule"] == "none"
            ),
            "persistence",
        )
    for row in d["results"]:
        require(
            set(row) == {"symbol", "id", "name", "ack"} and type(row["ack"]) is bool,
            "result keys",
        )
    roles = dict(
        v="v",
        id="id",
        mutation="kind",
        value="value",
        duration="duration",
        telegraph="telegraph",
        at="at",
    )
    require(
        len(d["request_fields"]) == len(roles)
        and {r["wire"] for r in d["request_fields"]} == set(roles),
        "request roles",
    )
    for row in d["request_fields"]:
        require(
            row["member"] == roles[row["wire"]]
            and row["type"] == ("mutation" if row["wire"] == "mutation" else "int"),
            "request field type",
        )
        require(
            set(row)
            == (
                {"wire", "member", "type"}
                if row["type"] == "mutation"
                else {"wire", "member", "type", "bounds"}
            ),
            "field keys",
        )
        if "bounds" in row:
            bounds(row["bounds"])
            require(row["bounds"][0] >= 0, "unsigned request field")
    for section in ("event_numbers", "vitals"):
        words([r["wire"] for r in d[section]])
        for row in d[section]:
            require(set(row) == {"wire", "bounds"}, "number keys")
            bounds(row["bounds"])
            require(
                row["bounds"][0] >= 0 or row["wire"] == "power", "unsigned event number"
            )
    bounds(d["ack_number_bounds"])
    require(d["ack_number_bounds"][0] >= 0, "unsigned ack number")
    require(
        d["reader_policy"]
        == dict(
            request_extra_fields="reject",
            event_extra_fields="preserve",
            vitals_optional=True,
            vitals_extra_fields="reject",
            duplicate_keys="reject_recursively",
            event_cap_measure="raw_len",
            detail_measure="python_characters",
        ),
        "unsupported reader policy",
    )


def macro(name, rows):
    return (
        "#define " + name + " \\\n" + " \\\n".join("    " + row for row in rows) + "\n"
    )


def render(d):
    validate(d)
    q = json.dumps
    h = [
        BEGIN,
        "/* Generated by scripts/generate_protocol_contract.py; do not edit. */",
    ]
    constants = {
        "MAX_REQUEST": d["limits"]["request_bytes"],
        "STATE_VERSION": d["versions"]["state"],
        "OBSERVATION_VERSION": d["observations"]["wire_version"],
        "REQUEST_VERSION": d["versions"]["request"],
        "EVENT_VERSION": d["versions"]["event"],
        "MAX_INT": d["limits"]["max_int"],
        "MAX_COUNTER": str(d["limits"]["max_counter"]) + "L",
        "REQUEST_STRING_BUFFER": d["limits"]["request_string_buffer"],
        "TURN_HEADROOM": d["limits"]["admission_turn_headroom"],
    }
    constants.update({"COSMETIC_" + k.upper(): v for k, v in d["cosmetic"].items()})
    constants.update({"BUDGET_" + k.upper(): v for k, v in d["budget"].items()})
    for row in d["non_effect_spenders"]:
        constants["SPEND_" + row["name"].upper()] = row["id"]
        constants["COST_" + row["name"].upper()] = row["cost"]
    h += [f"#define CHAOS_{k} {v}" for k, v in constants.items()]
    h += [
        "enum chaos_kind { "
        + ", ".join(f"{r['symbol']} = {r['id']}" for r in d["mutations"])
        + f", CHAOS_KINDS = {len(d['mutations'])}"
        + " };",
        "enum chaos_result { "
        + ", ".join(f"{r['symbol']} = {r['id']}" for r in d["results"])
        + " };",
    ]
    h += [
        "enum chaos_contract_rule { CHAOS_RULE_NONE, CHAOS_RULE_HALVE, CHAOS_RULE_DOUBLE };"
    ]
    h += [
        macro(
            "CHAOS_MUTATION_ROWS(X)",
            [
                "X("
                + ", ".join(
                    map(
                        str,
                        (
                            r["symbol"],
                            q(r["name"]),
                            r["cost"],
                            r["cosmetic_cost"],
                            *r["value"],
                            *r["duration"],
                            r["telegraph"],
                            -1
                            if r["engine_sanity_max"] is None
                            else r["engine_sanity_max"],
                            int(r["ordinary_food"]),
                            int(r["persistent"]),
                            "CHAOS_RULE_" + r["rule"].upper(),
                        ),
                    )
                )
                + ")"
                for r in d["mutations"]
            ],
        )
    ]
    h += [
        macro(
            "CHAOS_RESULT_ROWS(X)",
            [
                f"X({r['symbol']}, {q(r['name'])}, {int(r['ack'])})"
                for r in d["results"]
            ],
        )
    ]
    for key, field, name in (
        ("telegraphs", "id", "SIGNAL"),
        ("ambient_messages", "value", "AMBIENT_MESSAGE"),
    ):
        h += [
            macro(
                "CHAOS_" + name + "_ROWS(X)",
                [f"X({r[field]}, {q(r['text'])})" for r in d[key]],
            )
        ]
        h += [f"#define CHAOS_{name}_COUNT {len(d[key])}"]
    fields = d["request_fields"]
    h += [
        f"#define CHAOS_FIELD_COUNT {len(fields)}",
        f"#define CHAOS_FIELD_MASK {(1 << len(fields)) - 1}",
        "#define CHAOS_FIELD_NAMES " + ", ".join(q(r["wire"]) for r in fields),
        "#define CHAOS_MUTATION_FIELD "
        + str(next(i for i, r in enumerate(fields) if r["type"] == "mutation")),
    ]
    h += [
        macro(
            "CHAOS_ASSIGN_FIELDS(r, f)",
            [f"(r)->{r['member']} = (f)[{i}];" for i, r in enumerate(fields)],
        )
    ]
    h += [
        macro(
            "CHAOS_VALIDATE_FIELDS(r)",
            [
                f"if ((r)->{r['member']} < {r['bounds'][0]} || (r)->{r['member']} > {r['bounds'][1]}) return 0;"
                for r in fields
                if r["type"] == "int"
            ],
        )
    ]
    for key, prefix in (
        ("events", "EVENT"),
        ("phases", "PHASE"),
        ("ack_statuses", "STATUS"),
    ):
        h += [f"#define CHAOS_{prefix}_{s.upper()} {q(s)}" for s in d[key]]
    h += [f"#define CHAOS_STATUS_ADMITTED {q(d['journal_status'])}"]
    # Fixed typed serializer, not an interpreted schema. Order is reviewed data.
    types = dict(
        v="%d",
        seq="%ld",
        turn="%ld",
        safe="%ld",
        event="%s",
        phase="%s",
        detail="%s",
        sanity="%d",
        insight="%d",
        budget="%d",
        spent="%d",
        reserved="%d",
        last_id="%d",
        hp="%d",
        hp_max="%d",
        power="%d",
        power_max="%d",
        id="%d",
        status='"%s"',
        mutation='"%s"',
        value="%d",
        duration="%d",
        telegraph="%d",
        at="%d",
        cost="%d",
        cosmetic_cost="%d",
        expires="%ld",
    )

    def field(k):
        return q(k) + ":" + types[k]

    vitals = "{" + ",".join(field(r["wire"]) for r in d["vitals"]) + "}"
    event = (
        "{"
        + ",".join(
            '"vitals":' + vitals
            if k == "vitals"
            else '"cosmetic":{"seen":%d,"last_turn":%ld}'
            if k == "cosmetic"
            else field(k)
            for k in d["wire_order"]["event"]
        )
        + "%s}\n"
    )
    ack = "," + ",".join(field(k) for k in d["wire_order"]["ack_extra"])
    journal = (
        "{"
        + ",".join(
            '"v":' + str(d["versions"]["request"])
            if k == "v"
            else '"policy":' + str(d["cosmetic"]["policy"])
            if k == "policy"
            else field(k)
            for k in d["wire_order"]["journal_prefix"]
        )
        + "%s}\n"
    )
    h += [
        f"#define CHAOS_{name}_FORMAT {q(value)}"
        for name, value in (("EVENT", event), ("ACK", ack), ("JOURNAL", journal))
    ]
    o = d["observations"]
    for tag, rows in (
        ("operation", [o["operation_none"]] + o["families"]),
        ("stage", o["stages"]),
        ("fact", [o["fact_none"]] + o["facts"]),
    ):
        h += [
            "enum chaos_observation_"
            + tag
            + " { "
            + ", ".join(f"{r['symbol']} = {r['id']}" for r in rows)
            + " };"
        ]
    h += [
        "enum chaos_obs_channel { CHAOS_OBS_CHANNEL_MESSAGE = 1, CHAOS_OBS_CHANNEL_MAP = 2 };"
    ]
    h += [
        "enum chaos_obs_role { CHAOS_OBS_ROLE_ENABLE, CHAOS_OBS_ROLE_START, CHAOS_OBS_ROLE_NOTICE, CHAOS_OBS_ROLE_COMPLETE, CHAOS_OBS_ROLE_BLOCK };"
    ]
    h += [
        macro(
            "CHAOS_OBS_FAMILY_ROWS(X)",
            [
                f"X({r['symbol']}, {int(r['allow_blocked'])}, {q(r['name'])})"
                for r in o["families"]
            ],
        )
    ]
    h += [
        macro(
            "CHAOS_OBS_FACT_ROWS(X)",
            [
                f"X({r['symbol']}, {r['operation']}, CHAOS_OBS_CHANNEL_{r['channel'].upper()}, {int(r['implies_blocked'])}, {q(r['name'])})"
                for r in o["facts"]
            ],
        )
    ]
    h += [
        macro(
            "CHAOS_OBS_STAGE_ROWS(X)",
            [
                f"X({r['symbol']}, CHAOS_OBS_ROLE_{r['role'].upper()}, {q(r['name'])}, {q(r['phase'])})"
                for r in o["stages"]
            ],
        )
    ]
    h += [END]
    values = dict(
        LEGACY=d["legacy"],
        COSMETIC=d["cosmetic"],
        STATE_VERSION=d["versions"]["state"],
        OBSERVATION_VERSION=o["wire_version"],
        OBSERVATIONS=o,
        MAX_INT=d["limits"]["max_int"],
        FIELDS=tuple(r["wire"] for r in fields),
        REGISTRY={
            r["name"]: (r["cost"], r["director_sanity_max"], r["telegraph"])
            for r in d["mutations"]
        },
        MUTATIONS={r["name"]: r for r in d["mutations"]},
        NON_EFFECT_SPENDERS={
            r["name"]: (r["id"], r["cost"]) for r in d["non_effect_spenders"]
        },
        EVENTS=tuple(d["events"]),
        REASONS=tuple(r["name"] for r in d["results"] if r["ack"]),
        VITALS=tuple(r["wire"] for r in d["vitals"]),
        NUMBERS=tuple(r["wire"] for r in d["event_numbers"]),
        REQUEST_BOUNDS={
            r["wire"]: tuple(r["bounds"]) for r in fields if r["type"] == "int"
        },
        EVENT_BOUNDS={r["wire"]: tuple(r["bounds"]) for r in d["event_numbers"]},
        VITAL_BOUNDS={r["wire"]: tuple(r["bounds"]) for r in d["vitals"]},
        REQUEST_CAP=d["limits"]["request_bytes"],
        EVENT_CAP=d["limits"]["event_input_cap"],
        DETAIL_CAP=d["limits"]["event_detail_characters"],
        PHASES=tuple(d["phases"]),
        ACK_STATUSES=tuple(d["ack_statuses"]),
        ACK_NUMBERS=tuple(d["ack_numbers"]),
        ACK_BOUNDS=tuple(d["ack_number_bounds"]),
        REQUEST_VERSION=d["versions"]["request"],
        EVENT_VERSION=d["versions"]["event"],
    )
    py = "# Generated by scripts/generate_protocol_contract.py; do not edit.\n# ruff: noqa\n# fmt: off\n"
    for key, value in values.items():
        text = pprint.pformat(value, width=88, sort_dicts=False)
        if key in ("EVENTS", "REASONS"):
            text = "frozenset(" + text + ")"
        py += key + " = " + text + "\n"
    return "\n".join(h) + "\n", py


def generate(root, check=False):
    d = json.loads(
        (root / "chaos/protocol_contract.json").read_text(), object_pairs_hook=pairs
    )
    block, py = render(d)
    header = root / "include/chaos_protocol.h"
    old = header.read_text()
    if (
        old.count(BEGIN) != 1
        or old.count(END) != 1
        or old.index(BEGIN) >= old.index(END)
    ):
        raise ValueError("missing, duplicate or reversed generated markers")
    start, end = old.index(BEGIN), old.index(END) + len(END)
    outputs = {
        header: old[:start] + block.rstrip("\n") + old[end:],
        root / "chaos/_protocol_contract.py": py,
    }
    stale = False
    for path, content in outputs.items():
        current = path.read_text() if path.exists() else ""
        if current != content:
            stale = True
            if check:
                print(
                    "".join(
                        difflib.unified_diff(
                            current.splitlines(True),
                            content.splitlines(True),
                            fromfile=str(path),
                            tofile="generated",
                        )
                    ),
                    file=sys.stderr,
                )
            else:
                path.write_text(content)
    return 1 if check and stale else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        return generate(args.root, args.check)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"protocol contract: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
