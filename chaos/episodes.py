"""Offline v1/v2 row schemas; NetHack General Public License, see dat/license.

Parsing validates only a row, not history, root existence, same-operation/turn
linkage, marker sequencing, completion, or actual native delivery. Whistling
facts describe delivered wording, never ordinary/magic identity or obedience.
"""

from .protocol import MAX_INT, NUMBERS, VITALS, integer, parse_event, strict_json

_ENVELOPE = frozenset((*NUMBERS, "event", "phase", "detail", "vitals", "observation"))
_OBSERVATION = frozenset(("operation", "stage", "root_seq", "fact"))
_FACTS = {
    "whistling": frozenset(
        ("sound_high", "sound_shrill", "sound_normal", "sound_strange", "sound_humming")
    ),
    "fountain_drink": frozenset(
        ("water_refreshed", "water_foul", "cannot_reach", "detection_presented")
    ),
}


def parse_episode_event(raw) -> dict:
    """Validate one bounded JSON row, preserving the legacy v1 parser contract.

    V2 has a 4096-byte cap, including UTF-8 encoding of string input. V1 retains
    its original raw-input semantics, including optional vitals and extra keys.
    Returned legacy fields are not a redacted public projection.
    """
    if not isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("JSON text or bytes required")
    row = strict_json(raw, 4096)
    integer(row.get("v"))
    if row["v"] == 1:
        # The legacy parser indexes/hashes event directly. Validate this one
        # prerequisite so malformed rows raise ValueError, not KeyError/TypeError;
        # do not catch exceptions that could mask implementation bugs.
        if type(row.get("event")) is not str:
            raise ValueError("invalid legacy event name")
        return parse_event(raw)
    if row["v"] != 2:
        raise ValueError("unsupported observation version")
    if isinstance(raw, str):
        try:
            size = len(raw.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("invalid observation encoding") from exc
        if size > 4096:
            raise ValueError("JSON byte cap exceeded")
    if set(row) != _ENVELOPE:
        raise ValueError("invalid observation envelope fields")
    for key in NUMBERS:
        integer(row[key], 1 if key == "seq" else 0)
    if row["event"] != "observation" or row["detail"] != "":
        raise ValueError("invalid observation envelope")
    if row["sanity"] > 100 or any(
        row[key] > 12 for key in ("budget", "spent", "reserved")
    ):
        raise ValueError("invalid event budget or sanity")
    if row["reserved"] > row["spent"]:
        raise ValueError("invalid reservation")
    vitals = row["vitals"]
    if type(vitals) is not dict or set(vitals) != set(VITALS):
        raise ValueError("invalid vitals fields")
    for key in VITALS:
        integer(vitals[key], -MAX_INT if key == "power" else 0)
    payload = row["observation"]
    if type(payload) is not dict or set(payload) != _OBSERVATION:
        raise ValueError("invalid observation fields")
    operation, stage, fact = (payload[key] for key in ("operation", "stage", "fact"))
    if any(type(value) is not str for value in (operation, stage, fact)):
        raise ValueError("observation enums must be strings")
    root = integer(payload["root_seq"])
    if stage == "enabled":
        valid = operation == "none" and root == 0 and fact == "none"
    elif stage == "started":
        valid = operation in _FACTS and root == 0 and fact == "none"
    elif stage in ("notice", "completed", "blocked"):
        valid = operation in _FACTS and 0 < root < row["seq"]
        if stage == "notice":
            valid = valid and fact in _FACTS[operation]
        else:
            valid = valid and fact == "none"
            if stage == "blocked":
                valid = valid and operation == "fountain_drink"
    else:
        valid = False
    if not valid or row["phase"] != ("attempt" if stage == "started" else "result"):
        raise ValueError("invalid observation combination")
    return row
