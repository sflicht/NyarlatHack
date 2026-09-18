"""Host-built next-use composition. Not native admission and not free Lua."""

import copy
import hashlib
import json

from .next_use_history import next_use_menu

_EFFECTS = ("whistle_attention", "fountain_refresh")
_ALLOWED_OPS = frozenset(("quiet",) + _EFFECTS)


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
    frozen = [copy.deepcopy(row) for row in candidates]
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
