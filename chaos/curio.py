"""Pure offline curio authoring envelope and prompt composition. NGPL.

parse_envelope(raw_response) preserves the original JSON text and decoded Lua
UTF-8 bytes. It validates transport/schema bounds, NOT Lua syntax, returned
name/text, native admission, or placement. No repair or whisper normalization.
Source may contain Unicode and controls except NUL; only native Lua validation
can decide whether the exact source satisfies the hook contract.

compose_prompt(public_context, *, prior_notes=(), literary_layer="poe") returns
separate trusted instructions and a JSON user payload for a later caller.
Public context is an exact dict: required sanity (int 0..100), insight (int
0..1000000); optional role/race (nonblank printable ASCII, 1..32 bytes). Only
player-observable values supplied by the host belong here; no discovery occurs.
Prior notes are a list/tuple of at most six exact dicts with candidate_id
(lowercase SHA-256 hex of exact source), status, and continuity_note. Status is
one of authored/installed/admitted/rejected/placed. These are HOST metadata,
not fields the model envelope can assign. The caller must validate receipts,
source identity and ordering before calling: this module checks schema, not
persistence/status authenticity. Task 7b owns evidence and rollback handling.

Notes allow empty strings and Unicode whitespace except control characters.
"No controls" means Unicode General Category Cc: U+0000..001F, U+007F..009F.
Other valid Unicode is preserved without normalization. Each note is <=512
UTF-8 bytes. Raw JSON and combined instructions+user payload each have an
8192-byte UTF-8 cap, matching OAuthBackend.generate; decoded source is 1..4096
bytes. Escaping can exceed transport caps even when decoded fields fit. Reject
rather than truncate, select notes, or rewrite text. Prompt files are trusted
package resources chosen through a closed literary whitelist, never model paths.

No inference, credentials, ledger, installation or native-validation side effects.
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re


MAX_SOURCE_BYTES = 4096
MAX_NOTE_BYTES = 512
MAX_PRIOR_NOTES = 6
MAX_RESPONSE_BYTES = 8192
MAX_PROMPT_BYTES = 8192

_PROMPTS = Path(__file__).resolve().parent / "prompts" / "curio"
_LITERARY_FILES = {
    "poe": "poe.txt",
    "wilde": "wilde.txt",
    "carroll": "carroll.txt",
    "mackay": "mackay.txt",
    "abbott": "abbott.txt",
    "chambers": "chambers.txt",
    "gilman": "gilman.txt",
    "hodgson": "hodgson.txt",
}
_STATUSES = frozenset({"authored", "installed", "admitted", "rejected", "placed"})
_CANDIDATE_ID = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AuthoringEnvelope:
    """Validated authoring transport, not a validated/admitted Lua program."""

    raw_response: str
    lua_source: bytes
    continuity_note: str


@dataclass(frozen=True)
class AuthoringPrompt:
    """Keep instructions in the trusted/system channel, prompt in the user channel."""

    instructions: str
    prompt: str


def _utf8(text, label, maximum, minimum=0):
    if type(text) is not str:
        raise ValueError(f"{label} must be a string")
    # A Unicode scalar encodes to at least one byte; bound work before encoding.
    if not minimum <= len(text) <= maximum:
        raise ValueError(f"{label} must be {minimum}..{maximum} UTF-8 bytes")
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must be valid UTF-8 (no lone surrogates)") from exc
    if not minimum <= len(raw) <= maximum:
        raise ValueError(f"{label} must be {minimum}..{maximum} UTF-8 bytes")
    return raw


def _note(text):
    _utf8(text, "continuity_note", MAX_NOTE_BYTES)
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in text):
        raise ValueError("continuity_note must not contain Unicode Cc controls")
    return text


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON field")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError("non-JSON numeric constant")


def parse_envelope(raw_response):
    """Decode exactly two string fields, retaining raw text and exact Lua bytes."""
    _utf8(raw_response, "raw response", MAX_RESPONSE_BYTES)
    try:
        obj = json.loads(
            raw_response,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("authoring response must be one JSON object") from exc
    if type(obj) is not dict or obj.keys() != {"lua_source", "continuity_note"}:
        raise ValueError(
            "authoring envelope requires exactly lua_source and continuity_note"
        )
    source = _utf8(obj["lua_source"], "lua_source", MAX_SOURCE_BYTES, minimum=1)
    if b"\0" in source:
        raise ValueError("lua_source must not contain NUL")
    return AuthoringEnvelope(raw_response, source, _note(obj["continuity_note"]))


def _public_context(public):
    required = {"sanity", "insight"}
    if (
        type(public) is not dict
        or not required <= public.keys()
        or not public.keys() <= required | {"role", "race"}
    ):
        raise ValueError(
            "public_context requires sanity/insight and only optional role/race"
        )
    for key, maximum in (("sanity", 100), ("insight", 1000000)):
        if type(public[key]) is not int or not 0 <= public[key] <= maximum:
            raise ValueError(f"public_context {key} must be an integer in 0..{maximum}")
    for key in ("role", "race"):
        if key in public:
            text = public[key]
            _utf8(text, f"public_context {key}", 32, minimum=1)
            if any(not 32 <= ord(char) <= 126 for char in text) or not text.strip(" "):
                raise ValueError(
                    f"public_context {key} must be nonblank printable ASCII"
                )
    return dict(public)


def _prior_notes(notes):
    if type(notes) not in (list, tuple) or len(notes) > MAX_PRIOR_NOTES:
        raise ValueError(
            "prior_notes must be a list/tuple of at most six host-tagged notes"
        )
    result = []
    for note in notes:
        if type(note) is not dict or note.keys() != {
            "candidate_id",
            "status",
            "continuity_note",
        }:
            raise ValueError(
                "prior_notes require exactly candidate_id, status, continuity_note"
            )
        identity = note["candidate_id"]
        if type(identity) is not str or _CANDIDATE_ID.fullmatch(identity) is None:
            raise ValueError(
                "prior_notes candidate_id must be 64 lowercase SHA-256 hex digits"
            )
        status = note["status"]
        if type(status) is not str or status not in _STATUSES:
            raise ValueError(
                "prior_notes status is not a supported host lifecycle label"
            )
        result.append(
            {
                "candidate_id": identity,
                "status": status,
                "continuity_note": _note(note["continuity_note"]),
            }
        )
    return result


def compose_prompt(public_context, *, prior_notes=(), literary_layer="poe"):
    """Compose bounded trusted files + quoted public data; never call a model.

    Supply the latest host-verified notes in caller-selected order. Every supplied
    note is retained or the call fails. Schema validation does not authenticate
    host input or establish that anything was admitted, placed, or seen.
    """
    if type(literary_layer) is not str or literary_layer not in _LITERARY_FILES:
        raise ValueError("unknown literary layer; choose an exact supported name")
    public = _public_context(public_context)
    notes = _prior_notes(prior_notes)
    instructions = "\n\n".join(
        (_PROMPTS / name).read_text(encoding="utf-8")
        for name in ("contract.txt", "gothic.txt", _LITERARY_FILES[literary_layer])
    )
    prompt = json.dumps(
        {"public_context": public, "prior_notes": notes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    _utf8(instructions + prompt, "combined prompt", MAX_PROMPT_BYTES)
    return AuthoringPrompt(instructions, prompt)
