"""Bounded, strict reader for the private native next-use value journal (NGPL).

Hashes cover EXACT payload bytes, not sorted JSON/JCS. This is a value codec,
not native replay, admission, or executable/VM state. A terminal footer proves
structural completeness ONLY: a file cannot attest that its final fsync/close
succeeded. Consult the separately observed runtime capture status for that.
"""

import base64
import binascii
import hashlib
import json
import re
from pathlib import Path

MAX_BYTES = 8388608
MAX_LINE = 32768
MAX_RECORDS = 4096
I32 = 2147483647
I64 = 9223372036854775807


class JournalError(ValueError):
    """Malformed, inconsistent, unsupported, or over-limit journal."""


def _require(ok, message):
    if not ok:
        raise JournalError(message)


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names.split()), "field set")


def _integer(value, lo=0, hi=I32):
    _require(type(value) is int and lo <= value <= hi, "integer range/type")


def _hash(value):
    _require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "digest format"
    )


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise JournalError("non-JSON constant: " + value)


_DECODER = json.JSONDecoder(object_pairs_hook=_pairs, parse_constant=_constant)


def _json(raw):
    try:
        return _DECODER.decode(raw)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise JournalError("invalid JSON") from exc


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical_digest(value):
    return _digest(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    )


# All scalar fields are explicitly named; additions require a protocol review.
_SNAPSHOT = """snapshot_v program_id phase slot_w slot_f w_runtime state delay_used
callback_ordinal witnessed attention_claimed whistle_count fountain_count next_seq
termination_emitted identity_unsafe callback_w callback_f last_root admission_move
program_expiry delay_until variant origin_w_live origin_f_live armed_m_id replay_cursor
origin_w origin_f origin_w_deadline origin_f_deadline run_token level_token
activation_monstermoves armed_root source_length source_sha256 binding_sha256 source_hex
journal_state journal_bytes journal_sha256 capture_incomplete"""
_POST = """phase delay_used delay_until termination_emitted identity_unsafe
pending_w_capture f_inflight witnessed attention_claimed callback_w callback_f
whistle_count fountain_count origin_w_live origin_f_live manifest_success armed_m_id
expected_manifest_m_id activation_monstermoves armed_root pending_w_root f_root
current_run_token current_level_token expected_manifest_root expected_notice_seq expected_end_seq"""
_TRANSITION = """replay_input_v expected_last_root activation_move notice_root
witness_notice_seq token_present root_present expected_result published pre_public
operation family root source_sha256 callback_ordinal state seq slot_w slot_f w_runtime
m_id at_move fountain_outcome run_token level_token origin_w_live origin_f_live
whistle_count fountain_count end_reason expected_attention decision_root cursor
manifest_root notice_seq end_seq manifestation_delivered displaced invalid expected_token
post private_count public_count private_records public_records"""
_BOOL = set(
    """delay_used witnessed attention_claimed termination_emitted identity_unsafe
callback_w callback_f origin_w_live origin_f_live token_present root_present
expected_result published pre_public expected_attention manifestation_delivered displaced
invalid pending_w_capture f_inflight manifest_success active remap consumed
reason_present intent_present intent_sha256_present failure_code_present delay_used_after""".split()
)
_RANGES = {
    "snapshot_v": (5, 5),
    "journal_state": (0, 0),
    "journal_bytes": (0, 0),
    "capture_incomplete": (0, 0),
    "replay_input_v": (1, 1),
    "next_use_private_v": (2, 2),
    "next_use_public_v": (2, 2),
    "program_id": (1, I32),
    "phase": (3, 4),
    "slot_w": (0, 9),
    "slot_f": (0, 10),
    "w_runtime": (0, 7),
    "state": (0, 3),
    "state_before": (0, 3),
    "state_after": (0, 3),
    "callback_ordinal": (0, 2),
    "whistle_count": (0, 3),
    "fountain_count": (0, 2),
    "variant": (0, 2),
    "next_seq": (3, 17),
    "seq": (1, 16),
    "source_length": (1, 4096),
    "operation": (1, 13),
    "family": (0, 2),
    "fountain_outcome": (0, 6),
    "end_reason": (0, 7),
    "cursor": (1, MAX_RECORDS),
    "replay_cursor": (0, MAX_RECORDS),
    "private_count": (0, 4),
    "public_count": (0, 1),
    "armed_m_id": (0, 4294967295),
    "m_id": (0, 4294967295),
    "expected_manifest_m_id": (0, 4294967295),
    "run_token": (0, I64),
    "current_run_token": (0, I64),
    "validation": (0, 4),
    "failure_code": (0, 8),
    "trigger": (1, 2),
    "op": (0, 3),
    "operation_count": (1, 2),
    "cost": (1, 2),
}


def _scalars(value, names, nested=()):
    _keys(value, names)
    for key, item in value.items():
        if key in nested:
            continue
        if key.endswith("sha256"):
            _hash(item)
        else:
            lo, hi = (0, 1) if key in _BOOL else _RANGES.get(key, (0, I32))
            _integer(item, lo, hi)


def _snapshot(s):
    _scalars(s, _SNAPSHOT, ("source_hex", "journal_sha256"))
    _require(s["journal_sha256"] == "", "initial journal anchor")
    text = s["source_hex"]
    _require(
        type(text) is str
        and len(text) == 2 * s["source_length"]
        and re.fullmatch(r"[0-9a-f]+", text),
        "source hex/length",
    )
    source = bytes.fromhex(text)
    _require(_digest(source) == s["source_sha256"], "source digest")
    binding = "next-use-bind-v1|" + "|".join(
        str(s[k])
        for k in (
            "program_id",
            "source_sha256",
            "admission_move",
            "program_expiry",
            "variant",
            "run_token",
            "level_token",
            "origin_w",
            "origin_w_deadline",
            "origin_f",
            "origin_f_deadline",
        )
    )
    _require(_digest(binding.encode()) == s["binding_sha256"], "snapshot binding")
    _require(
        s["phase"] == 3
        and s["next_seq"] == 3
        and s["program_expiry"] == s["admission_move"] + 100
        and s["run_token"] > 0
        and s["level_token"] > 0,
        "initial snapshot",
    )
    for key in (
        "state delay_used callback_ordinal witnessed attention_claimed termination_emitted "
        "identity_unsafe callback_w callback_f last_root delay_until armed_m_id replay_cursor "
        "activation_monstermoves armed_root w_runtime"
    ).split():
        _require(s[key] == 0, "noninitial snapshot: " + key)
    for family in ("w", "f"):
        slot = s["slot_" + family]
        _integer(slot, 0, 1)
        _require(s["origin_" + family + "_live"] == slot, "initial live origin")
        _require((s["origin_" + family] > 0) == bool(slot), "origin slot binding")
        if not slot:
            _require(s["origin_" + family + "_deadline"] == 0, "undeclared deadline")
    _require(s["slot_w"] or s["slot_f"], "no declared slot")
    return source


def _private(r, s, seq):
    _scalars(
        r,
        "next_use_private_v kind seq at_move program_id source_sha256 data",
        ("data",),
    )
    _require(
        r["seq"] == seq
        and r["program_id"] == s["program_id"]
        and r["source_sha256"] == s["source_sha256"],
        "private identity/sequence",
    )
    _require(r["at_move"] >= s["admission_move"], "private time")
    d, kind = r["data"], r["kind"]
    if kind == 1:
        _scalars(d, "outcome reason reason_present")
        _require(d == {"outcome": 1, "reason": 0, "reason_present": 0}, "attempt")
    elif kind == 2:
        _scalars(
            d,
            "at_safe cost operation_count program_expiry envelope_b64 envelope_sha256 operations origin_roots",
            ("envelope_b64", "operations", "origin_roots"),
        )
        for key in ("operations", "origin_roots"):
            _require(
                type(d[key]) is list and len(d[key]) == d["operation_count"],
                "admission counts",
            )
            for item in d[key]:
                _integer(item, 1)
        _require(
            d["operations"] in ([1], [2], [1, 2]) and d["cost"] == d["operation_count"],
            "admission operations",
        )
        _require(d["program_expiry"] == s["program_expiry"], "admission expiry")
    elif kind == 3:
        _scalars(
            d,
            "callback_ordinal trigger validation failure_code root state_before state_after delay_used_after context_sha256 intent_present intent_sha256 intent_sha256_present failure_code_present intent",
            ("intent", "intent_sha256"),
        )
        _scalars(d["intent"], "op state")
        _require(d["intent_present"] == d["intent_sha256_present"], "intent presence")
        if d["intent_present"]:
            _hash(d["intent_sha256"])
            name = ("quiet", "delay", "whistle_attention", "fountain_refresh")[
                d["intent"]["op"]
            ]
            _require(
                d["intent_sha256"]
                == _canonical_digest(
                    {"next_use_intent_v": 2, "op": name, "state": d["intent"]["state"]}
                ),
                "intent digest",
            )
        else:
            _require(
                d["intent_sha256"] == "" and d["intent"] == {"op": 0, "state": 0},
                "absent intent",
            )
        _require(
            d["failure_code_present"] == int(d["failure_code"] != 0), "failure presence"
        )
        if d["validation"] == 0:
            _require(
                d["intent_present"]
                and not d["failure_code_present"]
                and d["state_after"] == d["intent"]["state"],
                "valid intent",
            )
        else:
            _require(
                d["state_after"] == d["state_before"], "invalid intent changed state"
            )
    elif kind == 4:
        _scalars(d, "family outcome root activation_monstermoves m_id")
        _integer(d["family"], 1, 2)
        _integer(
            d["outcome"], 1 if d["family"] == 1 else 7, 6 if d["family"] == 1 else 12
        )
        # Only autonomous W endings can carry the NULL-root sentinel;
        # operation/reason and pre/poststate are checked in _transition.
        _require(
            d["root"] > 0 or (d["family"] == 1 and d["outcome"] in (4, 5)),
            "effect root",
        )
    elif kind == 5:
        _scalars(d, "failure_code reason slot_f slot_w w_runtime")
        _integer(d["reason"], 1, 7)
        _require(
            d["slot_w"] != 1 and d["slot_f"] != 1 and d["w_runtime"] != 1,
            "terminal slots",
        )
    else:
        raise JournalError("private kind")


def _envelope(d, s, source):
    b64 = d["envelope_b64"]
    _require(type(b64) is str and 0 < len(b64) <= 10924, "envelope size/type")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise JournalError("envelope base64") from exc
    _require(
        0 < len(raw) <= 8192 and base64.b64encode(raw).decode() == b64,
        "envelope encoding",
    )
    _require(_digest(raw) == d["envelope_sha256"], "envelope digest")
    e = _json(raw.decode("utf-8"))
    _keys(
        e,
        "at cost id next_use_program_v operations origin_refs source source_sha256 telegraph ttl variant",
    )
    for key, lo, hi in (
        ("at", 0, I32),
        ("cost", 1, 2),
        ("id", 1, I32),
        ("next_use_program_v", 2, 2),
        ("ttl", 100, 100),
        ("variant", 0, 2),
    ):
        _integer(e[key], lo, hi)
    _require(
        type(e["source"]) is str
        and e["source"].encode("utf-8") == source
        and e["source_sha256"] == s["source_sha256"],
        "envelope source binding",
    )
    ops = [name for name, key in (("W", "slot_w"), ("F", "slot_f")) if s[key]]
    _require(
        e["operations"] == ops
        and d["operations"] == [1 if f == "W" else 2 for f in ops]
        and e["cost"] == d["cost"]
        and e["id"] == s["program_id"]
        and e["variant"] == s["variant"]
        and e["at"] == d["at_safe"]
        and e["telegraph"] == "next-use-v2-" + "".join(ops),
        "envelope admission binding",
    )
    _require(
        type(e["origin_refs"]) is list and len(e["origin_refs"]) == len(ops),
        "origin count",
    )
    run = None
    for i, (family, origin) in enumerate(zip(ops, e["origin_refs"])):
        _keys(
            origin,
            "end_seq fact family level_dlevel level_dnum move notice_seq root run",
        )
        for key in ("end_seq", "notice_seq", "root"):
            _integer(origin[key], 1)
        _integer(origin["move"])
        _integer(origin["level_dlevel"], 0, 255)
        _integer(origin["level_dnum"], 0, 255)
        _hash(origin["run"])
        _require(
            origin["root"] < origin["notice_seq"] < origin["end_seq"], "origin order"
        )
        _require(
            origin["family"] == family
            and origin["fact"]
            == ("ordinary_whistle" if family == "W" else "water_refreshed"),
            "origin family",
        )
        key = "origin_" + family.lower()
        _require(
            origin["root"] == s[key] == d["origin_roots"][i]
            and origin["move"] + 100 == s[key + "_deadline"]
            and origin["move"] <= s["admission_move"] <= s[key + "_deadline"],
            "origin binding",
        )
        _require(
            s["level_token"]
            == (origin["level_dnum"] + 1) * 100000 + origin["level_dlevel"],
            "level binding",
        )
        _require(run is None or run == origin["run"], "origin run binding")
        run = origin["run"]


def _autonomous_w_end(t, s, prior, effect):
    """NULL-root endings from runtime_end_w_impl, including nested captures."""
    operation, reason, p = t["operation"], 0, t["post"]
    if operation == 13 and not t["root_present"]:
        reason = t["end_reason"] if 1 <= t["end_reason"] <= 5 else 0
    elif operation == 8:
        reason = t["end_reason"] if 2 <= t["end_reason"] <= 5 else 0
    elif operation in (1, 7):
        # runtime_runtime_boundary_impl's precedence, also nested in ACTION.
        if p["current_level_token"] != s["level_token"]:
            reason = 2
        elif (
            p["current_run_token"] != s["run_token"]
            or (s["origin_w"] and not p["origin_w_live"])
            or (s["origin_f"] and not p["origin_f_live"])
        ):
            reason = 3
        elif any(
            s["origin_" + f] and t["at_move"] > s["origin_" + f + "_deadline"]
            for f in ("w", "f")
        ):
            reason = 4
        elif t["at_move"] >= s["program_expiry"]:
            reason = 5
        elif t["at_move"] >= prior["activation_monstermoves"] + 10:
            reason = 1
    elif operation in (4, 9) and t["at_move"] >= prior["activation_monstermoves"] + 10:
        reason = 1  # decision_ready, possibly nested in W_DECISION
    _require(
        reason != 0
        and prior["w_runtime"] == 1
        and t["w_runtime"] == {1: 2, 2: 4, 3: 3, 4: 3, 5: 3}.get(reason)
        and effect["outcome"] == (4 if prior["witnessed"] else 5)
        and effect["m_id"] == prior["armed_m_id"] == p["armed_m_id"]
        and effect["activation_monstermoves"]
        == prior["activation_monstermoves"]
        == p["activation_monstermoves"],
        "autonomous W ending",
    )


def _transition(t, s, seq, prior):
    _scalars(
        t, _TRANSITION, ("expected_token", "post", "private_records", "public_records")
    )
    _require(t["source_sha256"] == s["source_sha256"], "transition source")
    _scalars(t["expected_token"], "root active remap consumed")
    token = t["expected_token"]
    if t["operation"] == 1:
        if t["family"] == 2 and t["expected_result"] and t["token_present"]:
            _require(
                token == {"root": t["root"], "active": 1, "remap": 1, "consumed": 0},
                "action token binding",
            )
        else:
            _require(
                token == {"root": 0, "active": 0, "remap": 0, "consumed": 0},
                "absent action token",
            )
    elif not t["token_present"]:
        _require(
            token == {"root": 0, "active": 0, "remap": 0, "consumed": 0}, "absent token"
        )
    p = t["post"]
    _scalars(p, _POST)
    _require(p["termination_emitted"] == int(p["phase"] == 4), "terminal phase")
    _require(
        t["callback_ordinal"] == p["callback_w"] + p["callback_f"], "callback count"
    )
    _require(not p["witnessed"] or p["attention_claimed"], "witness without attention")
    _require(p["delay_used"] or p["delay_until"] == 0, "delay state")
    for key, count in (
        ("private_records", "private_count"),
        ("public_records", "public_count"),
    ):
        _require(type(t[key]) is list and len(t[key]) == t[count], "record count")
    terminal = False
    state = prior["state"]
    for r in t["private_records"]:
        _require(
            type(r) is dict and not terminal and r.get("kind") in (3, 4, 5),
            "transition private kind/order",
        )
        seq += 1
        _private(r, s, seq)
        _require(r["at_move"] == t["at_move"], "private transition time")
        d = r["data"]
        if r["kind"] == 3:
            _require(
                t["operation"] == 1
                and d["trigger"] == t["family"]
                and d["root"] == t["root"]
                and d["state_before"] == state
                and d["callback_ordinal"] == t["callback_ordinal"],
                "intent transition binding",
            )
            age = t["at_move"] - s["admission_move"]
            _require(
                0 <= age < 100 and t["at_move"] < s["program_expiry"],
                "callback age/expiry",
            )
            context = {
                "age": age,
                "fountain_count": prior["fountain_count"],
                "next_use_context_v": 2,
                "own_witnessed": "W" if prior["witnessed"] else "none",
                "source_sha256": s["source_sha256"],
                "state": state,
                "trigger": "W" if d["trigger"] == 1 else "F",
                "variant": s["variant"],
                "whistle_count": prior["whistle_count"],
            }
            _require(
                d["context_sha256"] == _canonical_digest(context), "context digest"
            )
            state = d["state_after"]
        elif r["kind"] == 4 and d["family"] == 1 and d["root"] == 0:
            _autonomous_w_end(t, s, prior, d)
        elif r["kind"] == 4 and d["family"] == 2:
            _require(
                t["operation"] == 6
                and t["token_present"]
                and token["active"]
                and prior.get("f_inflight") == 1
                and not p["f_inflight"]
                and d["root"] == token["root"] == prior["f_root"]
                and d["outcome"] == t["fountain_outcome"] + 6,
                "fountain effect binding",
            )
            outcome = t["fountain_outcome"]
            _require(
                t["slot_f"] == (3 if outcome <= 3 else 7 if outcome <= 5 else 2),
                "fountain outcome slot",
            )
            if outcome == 6:
                _require(token["consumed"] == 1, "remap without consumed token")
        elif r["kind"] == 5:
            terminal = True
            _require(
                all(d[k] == t[k] for k in ("slot_w", "slot_f", "w_runtime")),
                "terminal binding",
            )
    _require(t["seq"] == seq and t["state"] == state, "transition sequence/state")
    _require(
        bool(p["termination_emitted"])
        == (bool(prior["termination_emitted"]) or terminal),
        "missing terminal evidence",
    )
    witnesses = [
        r["data"]
        for r in t["private_records"]
        if r["kind"] == 4 and r["data"]["family"] == 1 and r["data"]["outcome"] == 3
    ]
    _require(
        len(witnesses)
        == t["public_count"]
        == int(p["witnessed"] and not prior["witnessed"]),
        "W witness carriers/poststate",
    )
    for r in t["public_records"]:
        _scalars(
            r, "next_use_public_v family phase root notice_seq end_seq", ("phase",)
        )
        _integer(r["phase"], 1, 1)
        _require(
            r["family"] == 1 and 0 < r["root"] < r["notice_seq"] < r["end_seq"],
            "public witness",
        )
        effect = witnesses[0]
        # runtime manifestation_begin/notice/end and on_manifestation.
        # Delivery/displacement alone is not publication; a later no-op
        # finalizer may retain a previously witnessed state without publishing.
        _require(
            s["slot_w"] == 1
            and t["operation"] == 5
            and t["expected_result"]
            and t["published"]
            and t["pre_public"]
            and t["manifestation_delivered"]
            and t["displaced"]
            and not t["invalid"]
            and prior["w_runtime"] == t["w_runtime"] == 1
            and prior["attention_claimed"]
            and p["attention_claimed"]
            and t["slot_w"] == 2
            and 0
            < t["m_id"]
            == prior["expected_manifest_m_id"]
            == prior["armed_m_id"]
            == p["armed_m_id"]
            == p["expected_manifest_m_id"]
            == effect["m_id"]
            and effect["activation_monstermoves"]
            == prior["activation_monstermoves"]
            == p["activation_monstermoves"]
            and r["root"]
            == t["root"]
            == t["manifest_root"]
            == t["notice_root"]
            == effect["root"]
            and r["notice_seq"] == t["notice_seq"] == t["witness_notice_seq"]
            and r["end_seq"] == t["end_seq"]
            and not any(
                p[k]
                for k in (
                    "manifest_success",
                    "expected_manifest_root",
                    "expected_notice_seq",
                    "expected_end_seq",
                )
            ),
            "public W manifestation binding",
        )
    return seq, dict(p, state=t["state"], w_runtime=t["w_runtime"]), terminal


def read_journal(path, *, capture_status=None):
    """Return validated values, separating bytes from capture acknowledgement.

    Without separately observed runtime evidence, a terminal footer yields only
    `structurally_complete` and `capture_acknowledged=None`. Optional
    `capture_status` must be the trusted final status of THIS capture, not a
    field read from the journal, a later attempt, or guessed from its footer.
    An acknowledgement is evidence of successful writer syscalls, not a claim
    about hardware surviving a crash. This function does not authenticate the
    caller's evidence and is not native playback verification.
    """
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        _require(0 < len(raw) <= MAX_BYTES, "journal byte bound")
        lines = raw.splitlines(keepends=True)
        _require(len(lines) <= MAX_RECORDS + 2, "journal record bound")
        records, previous = [], "0" * 64
        seq, ended, terminal = 2, False, False
        s = prior = None
        for index, line in enumerate(lines):
            _require(not ended, "trailing data after end")
            _require(
                len(line) < MAX_LINE and line.endswith(b"\n"), "line bound/truncation"
            )
            text = line.decode("ascii")
            _require(text.startswith('{"payload":'), "outer encoding")
            payload, stop = _DECODER.raw_decode(text, 11)
            outer = _json(text)
            _keys(outer, "payload sha256")
            _hash(outer["sha256"])
            _require(outer["sha256"] == _digest(line[11:stop]), "payload digest")
            _keys(payload, "v kind cursor prev data")
            _integer(payload["v"], 1, 1)
            _integer(payload["cursor"], 0, MAX_RECORDS)
            _hash(payload["prev"])
            _require(payload["prev"] == previous, "chain digest")
            previous = outer["sha256"]
            kind, d = payload["kind"], payload["data"]
            if index == 0:
                _require(kind == "header" and payload["cursor"] == 0, "missing header")
                _keys(d, "snapshot private_records")
                s = d["snapshot"]
                source = _snapshot(s)
                rs = d["private_records"]
                _require(type(rs) is list and len(rs) == 2, "header carriers")
                for n, r in enumerate(rs, 1):
                    _private(r, s, n)
                    _require(
                        r["kind"] == n and r["at_move"] == s["admission_move"],
                        "header carrier binding",
                    )
                _envelope(rs[1]["data"], s, source)
                prior = s
            elif kind == "transition":
                _require(
                    payload["cursor"] == index and index <= MAX_RECORDS,
                    "transition cursor",
                )
                _require(type(d) is dict and d.get("cursor") == index, "inner cursor")
                seq, prior, terminal = _transition(d, s, seq, prior)
            elif kind == "end":
                _keys(d, "status terminal_seq")
                _integer(d["terminal_seq"], 1, 16)
                _require(
                    index > 1
                    and payload["cursor"] == index - 1
                    and terminal
                    and d["status"] == "complete"
                    and d["terminal_seq"] == seq,
                    "end binding",
                )
                last = records[-1]["data"]
                _require(
                    prior["phase"] == 4
                    and prior["termination_emitted"]
                    and not prior["pending_w_capture"]
                    and not prior["f_inflight"]
                    and last["slot_w"] != 1
                    and last["slot_f"] != 1
                    and last["w_runtime"] != 1,
                    "nonterminal end",
                )
                ended = True
            else:
                raise JournalError("record kind/order")
            records.append(payload)
        status = "structurally_complete" if ended else "incomplete"
        acknowledged = None
        if capture_status is not None:
            _keys(
                capture_status,
                "sink_connected incomplete transaction_open acknowledged_cursor",
            )
            for key in ("sink_connected", "incomplete", "transaction_open"):
                _integer(capture_status[key], 0, 1)
            cursor = capture_status["acknowledged_cursor"]
            _integer(cursor, 0, MAX_RECORDS)
            transitions = len(records) - 1 - int(ended)
            _require(cursor <= transitions, "capture cursor exceeds trace")
            if capture_status["incomplete"]:
                status, acknowledged = "capture_failed", False
            elif (
                ended
                and capture_status["sink_connected"]
                and not capture_status["transaction_open"]
            ):
                _require(
                    cursor == transitions,
                    "capture cursor lacks terminal acknowledgement",
                )
                status, acknowledged = "acknowledged_complete", True
        return {
            "status": status,
            "structurally_complete": ended,
            "capture_acknowledged": acknowledged,
            "records": records,
        }
    except JournalError:
        raise
    except (
        OSError,
        ValueError,
        UnicodeError,
        RecursionError,
        TypeError,
        KeyError,
    ) as exc:
        raise JournalError("invalid journal: " + str(exc)) from exc
