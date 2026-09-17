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
    LEGACY,
    COSMETIC,
)

LEGACY_EVENT_BOUNDS = {r["wire"]: r["bounds"] for r in LEGACY["event_numbers"]}
LEGACY_REASONS = frozenset(r["name"] for r in LEGACY["results"] if r["ack"])
LEGACY_REGISTRY = {
    r["name"]: (r["cost"], r["director_sanity_max"], r["telegraph"])
    for r in LEGACY["mutations"]
}


def event_request(event):
    """Envelope versions never identify request grammar/accounting policy."""
    return {k: REQUEST_VERSION if k == "v" else event[k] for k in FIELDS}


def validate_cosmetic(event):
    cosmetic = event.get("cosmetic")
    if type(cosmetic) is not dict or set(cosmetic) != {"seen", "last_turn"}:
        raise ValueError("invalid cosmetic fields")
    seen = integer(cosmetic["seen"], 0, COSMETIC["mask"])
    last = integer(cosmetic["last_turn"])
    if last > event["turn"] or (not seen and last):
        raise ValueError("invalid cosmetic clock")


def validate_transition(previous, event, *, restore=False):
    """Validate policy and cosmetic continuity, not proof of UI delivery.

    The full-history caller stages enabled markers until their session matches.
    Restore snapshots reconcile state only: they never synthesize receipts.
    """
    if previous is None:
        return
    current = event["v"] in (3, 4)
    if current != (previous["v"] in (3, 4)):
        raise ValueError("mixed accounting policies")
    if not current:
        return
    old, new = previous["cosmetic"], event["cosmetic"]
    if old["seen"] & new["seen"] != old["seen"]:
        raise ValueError("cosmetic bit rollback")
    if old["seen"] == new["seen"] and old != new:
        raise ValueError("cosmetic timestamp reset")
    if new["last_turn"] < old["last_turn"]:
        raise ValueError("cosmetic clock rollback")
    ambient = (
        event["event"] == "ack"
        and event["status"] == "accepted"
        and event["mutation"] == "ambient"
    )
    if ambient:
        bit = 1 << (event["value"] - 1)
        if (
            old["seen"] & bit
            or new["seen"] != old["seen"] | bit
            or new["last_turn"] != event["turn"]
            or (old["seen"] and event["turn"] - old["last_turn"] < COSMETIC["spacing"])
            or event["spent"] != previous["spent"]
            or event["reserved"] != previous["reserved"]
        ):
            raise ValueError("invalid ambient commit")
    elif old != new and not restore:
        raise ValueError("unexplained cosmetic spending")


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
    legacy = type(e.get("v")) is int and e["v"] == 1
    bounds = LEGACY_EVENT_BOUNDS if legacy else EVENT_BOUNDS
    for key in NUMBERS:
        integer(e.get(key), *bounds[key])
    if (
        e["v"] not in (1, EVENT_VERSION)
        or type(e.get("event")) is not str
        or e["event"] not in EVENTS
        or e.get("phase") not in PHASES
    ):
        raise ValueError("invalid event envelope")
    if type(e.get("detail")) is not str or len(e["detail"]) > DETAIL_CAP:
        raise ValueError("invalid event detail")
    if e["reserved"] > e["spent"]:
        raise ValueError("invalid reservation")
    if not legacy:
        validate_cosmetic(e)
    if "vitals" in e:
        vitals = e["vitals"]
        if type(vitals) is not dict or set(vitals) != set(VITALS):
            raise ValueError("invalid vitals fields")
        for key in VITALS:
            integer(vitals[key], *VITAL_BOUNDS[key])
    if e["event"] == "ack":
        for k in LEGACY["ack_numbers"] if legacy else ACK_NUMBERS:
            integer(e.get(k), *ACK_BOUNDS)
        if e.get("status") not in ACK_STATUSES or e["detail"] not in (
            LEGACY_REASONS if legacy else REASONS
        ):
            raise ValueError("invalid acknowledgement")
        if type(e.get("mutation")) is not str or e["mutation"] not in ("", *REGISTRY):
            raise ValueError("invalid acknowledgement mutation")
        if e["id"]:
            parse_request(encode_request(event_request(e)))
        if e["status"] == "accepted" and (not e["id"] or e["detail"] != "ok"):
            raise ValueError("invalid accepted acknowledgement")
        if not legacy:
            row = MUTATIONS.get(e["mutation"]) if e["id"] else None
            if (e["cost"], e["cosmetic_cost"]) != (
                (row["cost"], row["cosmetic_cost"]) if row else (0, 0)
            ):
                raise ValueError("incorrect registered acknowledgement tariffs")
            if e["phase"] != "result":
                raise ValueError("invalid acknowledgement phase")
            if not e["id"] and (
                e["mutation"] != ""
                or any(
                    e[k] for k in ("value", "duration", "telegraph", "at", "expires")
                )
            ):
                raise ValueError("invalid malformed-request sentinel")
            if e["status"] == "accepted":
                expires = e["turn"] + e["duration"] if e["duration"] else 0
                if (
                    e["last_id"] != e["id"]
                    or e["at"] != e["safe"]
                    or e["expires"] != expires
                ):
                    raise ValueError("inconsistent accepted acknowledgement")
            elif e["detail"] == "ok" or e["expires"]:
                raise ValueError("inconsistent rejected acknowledgement")
    return e
