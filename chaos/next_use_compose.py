"""Host-built next-use composition. Not native admission and not free Lua."""

import copy
import hashlib
import json

from .next_use_history import next_use_menu

_EFFECTS = ("whistle_attention", "fountain_refresh")
_ALLOWED_OPS = frozenset(("quiet",) + _EFFECTS)
_ROW_KEYS = frozenset(("family", "op", "origin"))
_ORIGIN_KEYS = frozenset(("root_seq", "notice_seq", "end_seq", "fact"))
_W_FACTS = frozenset(
    ("sound_high", "sound_shrill", "sound_normal", "sound_strange", "sound_humming")
)
_F_FACTS = frozenset(("water_refreshed",))
_FAMILY_OPS = {
    "W": frozenset(("quiet", "whistle_attention")),
    "F": frozenset(("quiet", "fountain_refresh")),
}
_FAMILY_FACTS = {"W": _W_FACTS, "F": _F_FACTS}
_SEQ_MAX = 2147483647


def _is_seq(value):
    return type(value) is int and 1 <= value <= _SEQ_MAX


def _typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _typed_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _typed_equal(a, b) for a, b in zip(left, right)
        )
    return left == right


def validate_next_use_row(row):
    """Exact current next-use row: types, chronology, and family/op/fact."""
    if type(row) is not dict or set(row) != _ROW_KEYS:
        raise ValueError("next-use row schema")
    family, op, origin = row["family"], row["op"], row["origin"]
    if type(family) is not str or type(op) is not str or type(origin) is not dict:
        raise ValueError("next-use row schema")
    if set(origin) != _ORIGIN_KEYS:
        raise ValueError("next-use origin schema")
    if not (
        _is_seq(origin["root_seq"])
        and _is_seq(origin["notice_seq"])
        and _is_seq(origin["end_seq"])
        and origin["root_seq"] < origin["notice_seq"] < origin["end_seq"]
    ):
        raise ValueError("next-use origin chronology")
    if type(origin["fact"]) is not str:
        raise ValueError("next-use origin fact")
    if family not in _FAMILY_OPS or op not in _FAMILY_OPS[family]:
        raise ValueError("next-use family or operation")
    if origin["fact"] not in _FAMILY_FACTS[family]:
        raise ValueError("next-use fact is not eligible for family")
    return row


def match_frozen_row(decoded, menu):
    """Return a deep copy of the trusted host row after a type-exact match."""
    validate_next_use_row(decoded)
    for row in menu:
        if _typed_equal(decoded, row):
            return copy.deepcopy(row)
    raise ValueError("history choice is outside the frozen candidate menu")


def composition_candidates(state):
    """At most two frozen choices: cross-family effects, else effect plus quiet."""
    menu = next_use_menu(state)
    effects = [row for row in menu if row["op"] in _EFFECTS]
    if len(effects) >= 2:
        return [copy.deepcopy(row) for row in effects[:2]]
    if len(effects) == 1:
        family = effects[0]["family"]
        quiet = [
            row for row in menu if row["family"] == family and row["op"] == "quiet"
        ]
        if quiet:
            return [copy.deepcopy(quiet[0]), copy.deepcopy(effects[0])]
        return [copy.deepcopy(effects[0])]
    return []


def lua_source(op):
    """One bounded on_action. The engine still owns legality."""
    if op not in _ALLOWED_OPS:
        raise ValueError("next-use op is outside the frozen composition menu")
    return (
        "return {\n"
        "  on_action = function(context)\n"
        f'    return {{next_use_intent_v=2, op="{op}", state=0}}\n'
        "  end\n"
        "}\n"
    )


def compose(selected):
    """Exact selected menu row to opaque source bytes and digest."""
    if type(selected) is not dict or selected.get("op") not in _ALLOWED_OPS:
        raise ValueError("composition requires an exact frozen next-use row")
    source = lua_source(selected["op"]).encode("ascii")
    if not 0 < len(source) <= 4096 or b"\0" in source:
        raise ValueError("source bounds violated")
    return dict(
        family=selected["family"],
        op=selected["op"],
        origin=copy.deepcopy(selected["origin"]),
        source=source.decode("ascii"),
        source_sha256=hashlib.sha256(source).hexdigest(),
        source_bytes=len(source),
    )


def freeze_menu(candidates):
    """Canonical copies; never let later mutation change the published menu."""
    if type(candidates) is not list or len(candidates) > 2:
        raise ValueError("bounded next-use candidate list required")
    frozen = [copy.deepcopy(validate_next_use_row(row)) for row in candidates]
    encoded = [
        json.dumps(
            row,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        for row in frozen
    ]
    if len(set(encoded)) != len(encoded):
        raise ValueError("duplicate next-use candidate")
    return frozen
