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


def _origin(state, operation, facts):
    if type(state) is not HistoryState:
        raise ValueError("checked history required")
    if not state.enabled:
        return None
    for group in state.episodes.get("episodes", ()):
        if group.get("operation") != operation:
            continue
        for row in group.get("evidence", ()):
            if (
                row.get("fact") in facts
                and type(row.get("root_seq")) is int
                and type(row.get("notice_seq")) is int
                and type(row.get("end_seq")) is int
            ):
                return dict(
                    root_seq=row["root_seq"],
                    notice_seq=row["notice_seq"],
                    end_seq=row["end_seq"],
                    fact=row["fact"],
                )
        return None
    return None


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
