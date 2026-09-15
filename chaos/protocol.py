"""Strict, bounded protocol v1. NetHack General Public License; see dat/license."""

import json
import re

MAX_INT = 2147483647
FIELDS = ("v", "id", "mutation", "value", "duration", "telegraph", "at")
REGISTRY = {
    "ambient": (1, 100, 1),
    "ward_efficacy": (4, 80, 2),
    "hunger_rate": (3, 90, 3),
}
EVENTS = frozenset(
    "eat read zap apply pray kill level_enter level_leave sanity insight death sleep session safe_point ack telegraph expiry haunting haunt_step backtrack curio".split()
)
REASONS = frozenset(
    "ok schema oversize duplicate schedule budget active ineligible log_failure".split()
)
VITALS = ("hp", "hp_max", "power", "power_max")
NUMBERS = (
    "v",
    "seq",
    "turn",
    "safe",
    "sanity",
    "insight",
    "budget",
    "spent",
    "reserved",
    "last_id",
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
    r = strict_json(raw, 512)
    if set(r) != set(FIELDS):
        raise ValueError("request fields do not match protocol")
    for k in FIELDS:
        if k != "mutation":
            integer(r[k], 1 if k in ("id", "at") else 0)
    name = r["mutation"]
    if type(name) is not str or name not in REGISTRY or r["v"] != 1:
        raise ValueError("unknown mutation or version")
    if r["telegraph"] != REGISTRY[name][2]:
        raise ValueError("registered telegraph required")
    if name == "ambient":
        valid = r["value"] in (1, 2, 3) and r["duration"] == 0
    else:
        valid = (
            r["value"] == (50 if name == "ward_efficacy" else 2)
            and 1 <= r["duration"] <= 50
        )
    if not valid:
        raise ValueError("mutation bounds violated")
    return r


def encode_request(r):
    raw = json.dumps(r, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    parse_request(raw)
    return raw


def parse_event(raw):
    e = strict_json(raw, 4096)
    for key in NUMBERS:
        integer(e.get(key), 1 if key == "seq" else 0)
    if (
        e["v"] != 1
        or e["event"] not in EVENTS
        or e.get("phase") not in ("attempt", "result")
    ):
        raise ValueError("invalid event envelope")
    if type(e.get("detail")) is not str or len(e["detail"]) > 256:
        raise ValueError("invalid event detail")
    if e["sanity"] > 100 or any(e[k] > 12 for k in ("spent", "reserved", "budget")):
        raise ValueError("invalid event budget or sanity")
    if e["reserved"] > e["spent"]:
        raise ValueError("invalid reservation")
    if "vitals" in e:
        vitals = e["vitals"]
        if type(vitals) is not dict or set(vitals) != set(VITALS):
            raise ValueError("invalid vitals fields")
        for key in VITALS:
            integer(vitals[key], -MAX_INT if key == "power" else 0)
    if e["event"] == "ack":
        for k in ("id", "value", "duration", "telegraph", "at", "cost", "expires"):
            integer(e.get(k))
        if (
            e.get("status") not in ("accepted", "rejected")
            or e["detail"] not in REASONS
        ):
            raise ValueError("invalid acknowledgement")
        if type(e.get("mutation")) is not str or e["mutation"] not in ("", *REGISTRY):
            raise ValueError("invalid acknowledgement mutation")
        if e["id"]:
            parse_request(encode_request({k: e[k] for k in FIELDS}))
        if e["status"] == "accepted" and (not e["id"] or e["detail"] != "ok"):
            raise ValueError("invalid accepted acknowledgement")
    return e
