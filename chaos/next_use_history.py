"""Public-episode next-use eligibility. Not native admission or a model call."""

from .history import HistoryState

_W_FACTS = frozenset(
    (
        "sound_high",
        "sound_shrill",
        "sound_normal",
        "sound_strange",
        "sound_humming",
    )
)
_F_FACTS = frozenset(("water_refreshed",))
_FAMILIES = (
    ("W", "whistling", _W_FACTS, ("quiet", "whistle_attention")),
    ("F", "fountain_drink", _F_FACTS, ("quiet", "fountain_refresh")),
)


def _latest(state, operation, facts):
    if type(state) is not HistoryState:
        raise ValueError("checked history required")
    if not state.enabled:
        return None
    # Native ownership changes on a qualifying notice, not on completion.
    # An unfinished newer notice must suppress the previous completed origin.
    for row in reversed(state._next_use_roots):
        if row["operation"] == operation and row["fact"] in facts:
            return row
    return None


def _origin(state, operation, facts):
    row = _latest(state, operation, facts)
    if row is None or not row["completed"]:
        return None
    return {key: row[key] for key in ("root_seq", "notice_seq", "end_seq", "fact")}


def pending_families(state):
    """Qualifying notices whose exact origin has not completed or blocked."""
    return tuple(
        family
        for family, operation, facts, _ops in _FAMILIES
        if (row := _latest(state, operation, facts)) is not None
        and row["end_seq"] is None
    )


def eligible_families(state):
    """Families with a live qualifying origin. Absence is not substitution."""
    found = []
    for family, operation, facts, _ops in _FAMILIES:
        if _origin(state, operation, facts) is not None:
            found.append(family)
    return tuple(found)


def next_use_menu(state):
    """Eligible (family, op) pairs. Ops are preference; families are eligibility."""
    menu = []
    for family, operation, facts, ops in _FAMILIES:
        origin = _origin(state, operation, facts)
        if origin is None:
            continue
        for op in ops:
            menu.append(dict(family=family, op=op, origin=dict(origin)))
    return menu
