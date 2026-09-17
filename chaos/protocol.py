"""Strict, bounded protocol v1. NetHack General Public License; see dat/license."""

import json
import re

from ._protocol_contract import (
    MAX_INT as MAX_INT,
    FIELDS as FIELDS,
    REGISTRY as REGISTRY,
    EVENTS as EVENTS,
    REASONS as REASONS,
    VITALS as VITALS,
    NUMBERS as NUMBERS,
    MUTATIONS,
    REQUEST_BOUNDS,
    EVENT_BOUNDS,
    VITAL_BOUNDS,
    REQUEST_CAP,
    EVENT_CAP,
    DETAIL_CAP,
    PHASES,
    ACK_STATUSES,
    ACK_NUMBERS,
    ACK_BOUNDS,
    REQUEST_VERSION,
    EVENT_VERSION,
)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw, cap):
    if len(raw) > cap:
        raise ValueError("JSON byte cap exceeded")

    def invalid(_):
        raise ValueError("invalid JSON number")

    try:
        result = json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as e:
        raise ValueError("invalid JSON") from e
    if type(result) is not dict:
        raise ValueError("JSON object required")
    return result


def integer(value, low=0, high=MAX_INT):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("integer outside protocol bounds")
    return value


def parse_request(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    # C accepts literal ASCII strings only, and canonical unsigned integers.
    if b"\\" in raw or any(c > 126 or (c < 32 and c not in (9, 10, 13)) for c in raw):
        raise ValueError("request must use literal ASCII")
    if re.search(rb":\s*-", raw):
        raise ValueError("signed integers forbidden")
    r = strict_json(raw, REQUEST_CAP)
    if set(r) != set(FIELDS):
        raise ValueError("request fields do not match protocol")
    for k in FIELDS:
        if k != "mutation":
            integer(r[k], *REQUEST_BOUNDS[k])
    name = r["mutation"]
    if type(name) is not str or name not in REGISTRY or r["v"] != REQUEST_VERSION:
        raise ValueError("unknown mutation or version")
    if r["telegraph"] != REGISTRY[name][2]:
        raise ValueError("registered telegraph required")
    row = MUTATIONS[name]
    valid = all(row[k][0] <= r[k] <= row[k][1] for k in ("value", "duration"))
    if not valid:
        raise ValueError("mutation bounds violated")
    return r


def encode_request(r):
    raw = json.dumps(r, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    parse_request(raw)
    return raw


def parse_event(raw):
    e = strict_json(raw, EVENT_CAP)
    for key in NUMBERS:
        integer(e.get(key), *EVENT_BOUNDS[key])
    if (
        e["v"] != EVENT_VERSION
        or e["event"] not in EVENTS
        or e.get("phase") not in PHASES
    ):
        raise ValueError("invalid event envelope")
    if type(e.get("detail")) is not str or len(e["detail"]) > DETAIL_CAP:
        raise ValueError("invalid event detail")
    if e["reserved"] > e["spent"]:
        raise ValueError("invalid reservation")
    if "vitals" in e:
        vitals = e["vitals"]
        if type(vitals) is not dict or set(vitals) != set(VITALS):
            raise ValueError("invalid vitals fields")
        for key in VITALS:
            integer(vitals[key], *VITAL_BOUNDS[key])
    if e["event"] == "ack":
        for k in ACK_NUMBERS:
            integer(e.get(k), *ACK_BOUNDS)
        if e.get("status") not in ACK_STATUSES or e["detail"] not in REASONS:
            raise ValueError("invalid acknowledgement")
        if type(e.get("mutation")) is not str or e["mutation"] not in ("", *REGISTRY):
            raise ValueError("invalid acknowledgement mutation")
        if e["id"]:
            parse_request(encode_request({k: e[k] for k in FIELDS}))
        if e["status"] == "accepted" and (not e["id"] or e["detail"] != "ok"):
            raise ValueError("invalid accepted acknowledgement")
    return e
