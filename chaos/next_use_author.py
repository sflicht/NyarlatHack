"""Offline next-use source authoring; fake transport only, never admission. NGPL.

Production requires the existing C parser and shared sandbox via an explicitly
supplied, trusted native library. There is no Python-parser fallback. The narrow
unit_fixture switch is for injected test validators and is marked in receipts.
No provider, configuration, credentials, native build or live chooser is used.
"""

import ctypes
import json
from pathlib import Path

from . import curio_store as store
from .director import Mailbox
from .episodes import parse_episode_event
from .history import public_context, snapshot_history
from .next_use_envelope import engine_run_hex, envelope_from_selection
from .next_use_history import next_use_menu
from .next_use_schedule import NextUseScheduler, _matches, host_from_schedule
from .protocol import strict_json

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "chaos/prompts"
SOURCE_REVISION = "17a02610838a1ba1ad35d31488d6929e599872f7"
PROMPT_VERSION = "next-use-offline-author-v1"
MAX_PROMPT_BYTES = 12288
MAX_RESPONSE_BYTES = 8192
MAX_SOURCE_BYTES = 4096
_NAMES = (
    "next_use-author-prompt.json",
    "next_use-author-response.json",
    "next_use-author-receipt.json",
    "next_use-envelope.json",
)
_SOURCE_FILES = {
    "include/chaos_next_use.h",
    "src/chaos_next_use.c",
    "src/chaos_next_use_runtime.c",
    "src/chaos_lua.c",
    "src/attrib.c",
    "src/u_init.c",
    "src/fountain.c",
    "src/dogmove.c",
    "chaos/history.py",
    "chaos/next_use_envelope.py",
    "chaos/next_use_history.py",
    "chaos/next_use_schedule.py",
}


class FakeAuthorTransport:
    """One exact supplied response. Not model authorship or a network adapter."""

    def __init__(self, response):
        if type(response) is not bytes:
            raise ValueError("exact response bytes required")
        self.response = response
        self.calls = []

    def generate(self, instructions, prompt):
        if self.calls:
            raise ValueError("offline author attempt already used; no retry")
        self.calls.append((instructions, prompt))
        return self.response


class _Author(ctypes.Structure):
    # include/chaos_next_use.h: struct chaos_next_use_author, not a new schema.
    _fields_ = [
        ("abstain", ctypes.c_int),
        ("source_length", ctypes.c_size_t),
        ("source", ctypes.c_char * (MAX_SOURCE_BYTES + 1)),
    ]


class NativeAuthorValidator:
    """Call existing C APIs in a host-reviewed library; does not build one.

    The caller owns library provenance/ABI compatibility. Library identity is
    recorded, not certification. Dedicated tests compile the real C parser and
    Lua loader and check this interface's structure layout and exact bytes.
    Load checks are not callback coverage, native effects, or admission.
    """

    def __init__(self, library):
        path = Path(library)
        if not path.is_absolute():
            raise ValueError("explicit absolute trusted native library required")
        self.library_sha256 = store._digest(path.read_bytes())
        self._library = ctypes.CDLL(str(path))
        self._parse = self._library.chaos_next_use_parse_author
        self._parse.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(_Author),
        ]
        self._parse.restype = ctypes.c_int
        self._load = self._library.chaos_lua_next_use_load
        self._load.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        self._load.restype = ctypes.c_int

    def parse_author(self, raw):
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE_BYTES:
            raise ValueError("author response byte cap")
        result = _Author()
        status = self._parse(raw, len(raw), ctypes.byref(result))
        if status != 0:
            raise ValueError(f"chaos_next_use_parse_author rejected: {status}")
        if result.abstain:
            return None
        if not 0 < result.source_length <= MAX_SOURCE_BYTES:
            raise ValueError("native author source length")
        return ctypes.string_at(
            ctypes.addressof(result) + _Author.source.offset, result.source_length
        )

    def load_source(self, source):
        status = self._load(source, len(source))
        if status != 0:
            raise ValueError(f"chaos_lua_next_use_load rejected: {status}")


def _instructions():
    """Conservative guide binding, not a repository-wide manifest.

    Whole-file hashes deliberately require a guide review even for unrelated
    edits within these few referenced files. That maintenance cost is accepted
    here rather than introducing a source-excerpt extraction framework.
    """
    manifest_raw = (PROMPTS / "next-use-mechanics-sources.json").read_bytes()
    manifest = strict_json(manifest_raw.decode("utf-8"), 4096)
    if (
        set(manifest) != {"revision", "files"}
        or manifest["revision"] != SOURCE_REVISION
        or type(manifest["files"]) is not dict
        or set(manifest["files"]) != _SOURCE_FILES
    ):
        raise ValueError("mechanics source binding")
    for name, digest in manifest["files"].items():
        if store._digest((ROOT / name).read_bytes()) != digest:
            raise ValueError("mechanics source changed; review guide before authoring")
    contract = (PROMPTS / "next-use-author.txt").read_bytes()
    guide = (PROMPTS / "next-use-mechanics.txt").read_bytes()
    task = (PROMPTS / "next-use-offline-author.txt").read_bytes()
    instructions = b"\n\n".join((task, contract, guide)).decode("utf-8")
    return instructions, {
        "prompt_version": PROMPT_VERSION,
        "source_revision": SOURCE_REVISION,
        "guide_sha256": store._digest(guide),
        "contract_sha256": store._digest(contract),
        "task_sha256": store._digest(task),
        "mechanics_sources_sha256": store._digest(manifest_raw),
    }


def _scheduled_templates(directory, fd, state, proof):
    # Reuse #143's bounded readers, exact chronology and identity checks. This
    # takes no seeded decision: the author receives host-selected capabilities.
    snapshot = NextUseScheduler(directory, seed=0)
    pending = snapshot._read(fd)
    if pending or snapshot.schedule.tail or state.ended or not state.enabled:
        raise ValueError("complete eligible scheduled origins required")
    event = proof["event"]
    if (
        list(snapshot.events.identity or ()) != event["identity"]
        or snapshot.events.offset != event["length"]
        or snapshot.events.digest.hex() != event["sha256"]
    ):
        raise ValueError("history changed during schedule selection")
    raw = store._read(fd, "next_use-schedule.jsonl", snapshot.schedule.max_bytes)
    if store._digest(raw) != snapshot.schedule.digest.hex():
        raise ValueError("schedule changed during selection")
    templates = []
    levels = set()
    # The envelope alone requires W,F order; schedule/history may have repeated
    # and mixed families. next_use_menu suppresses superseded/pending origins.
    for selected in next_use_menu(state):
        if selected["op"] != "quiet":
            continue
        matching = [row for row in snapshot.rows if _matches(row, selected)]
        if not matching:
            continue
        if len(matching) != 1:
            raise ValueError("ambiguous scheduled origin")
        schedule = matching[0]
        end = parse_episode_event(snapshot.lines[schedule["end_seq"] - 1])
        if end["safe"] != state.safe or end["last_id"] != state.last_id:
            continue  # Never move an old completion to a new admission window.
        host = host_from_schedule(
            schedule, engine_run_hex(directory), end["safe"] + 1, end["last_id"] + 1
        )
        templates.append(envelope_from_selection(selected, host)[0])
        levels.add((schedule["level_dnum"], schedule["level_dlevel"]))
    if not templates:
        raise ValueError("no eligible scheduled completion")
    if len(levels) != 1:
        raise ValueError("scheduled origins must share a level")
    return templates, raw, snapshot


def author_offline(directory, *, transport, validator=None, unit_fixture=False):
    """Author/publish once from private events+schedule; never admits a program.

    History and schedule are rechecked after the fake response. No retries,
    source repair or evidence overwrites. On failure, already published evidence
    remains and prevents reuse. Current public history exposes accepted ACKs and
    explicit expiry only; absent proposed/applied/witnessed evidence is not made up.
    """
    if type(transport) is not FakeAuthorTransport:
        raise ValueError("only the offline FakeAuthorTransport is supported")
    if type(unit_fixture) is not bool or validator is None:
        raise ValueError("native author parser and shared sandbox required")
    if not unit_fixture and type(validator) is not NativeAuthorValidator:
        raise ValueError("production requires NativeAuthorValidator; no fallback")
    with Mailbox(directory), store._directory(directory) as fd:
        if any(store._exists(fd, name) for name in _NAMES):
            raise ValueError("author evidence or candidate exists; no retry/clobber")
        state, proof = snapshot_history(directory)
        templates, schedule_raw, snapshot = _scheduled_templates(
            directory, fd, state, proof
        )
        operations = [row["operations"][0] for row in templates]
        capabilities = dict(
            operations=operations,
            cost=len(operations),
            ttl=100,
            state_min=0,
            state_max=3,
            uses_per_family=1,
            delay_uses=1,
            variant=0,
        )
        instructions, identities = _instructions()
        prompt = store._encode(
            dict(public_context=public_context(state), capabilities=capabilities)
        ).decode("utf-8")
        prompt_bytes = len((instructions + prompt).encode("utf-8"))
        if prompt_bytes > MAX_PROMPT_BYTES:
            raise ValueError("offline author prompt byte cap exceeded")
        prompt_raw = store._encode(dict(instructions=instructions, prompt=prompt))
        receipt = dict(
            **identities,
            mode="offline_handwritten_fixture",
            validation="unit_fixture_not_native"
            if unit_fixture
            else "native_parser_and_load",
            native_admission="unverified",
            prompt_sha256=store._digest(prompt_raw),
            prompt_bytes=prompt_bytes,
            capability_sha256=store._digest(store._encode(capabilities)),
            capabilities=capabilities,
            history_checkpoint=proof,
            schedule_sha256=store._digest(schedule_raw),
            source_sha256=None,
            attempted_envelope_sha256=None,
            envelope_sha256=None,
        )
        if not unit_fixture:
            receipt["validator_library_sha256"] = validator.library_sha256
        # Reservation is immutable and deliberately precedes the one attempt.
        store._publish(fd, _NAMES[0], prompt_raw)
        try:
            raw = transport.generate(instructions, prompt)
            if type(raw) is not bytes:
                raise ValueError("exact response bytes required")
            receipt.update(response_sha256=store._digest(raw), response_bytes=len(raw))
            if not 0 < len(raw) <= MAX_RESPONSE_BYTES:
                raise ValueError("author response byte cap")
            store._publish(fd, _NAMES[1], raw)
            source = validator.parse_author(raw)
            if source is not None:
                if (
                    type(source) is not bytes
                    or not 0 < len(source) <= MAX_SOURCE_BYTES
                    or b"\0" in source
                ):
                    raise ValueError("author source bounds")
                validator.load_source(source)
                receipt["source_sha256"] = store._digest(source)
            # Require the entire snapshot unchanged, not merely an old prefix:
            # appended events could invalidate eligibility or host scheduling.
            _, current_proof = snapshot_history(directory)
            snapshot._read(fd)  # Retain schedule identity/prefix checks too.
            if (
                current_proof != proof
                or snapshot.events.digest.hex() != proof["event"]["sha256"]
                or snapshot.schedule.digest.hex() != store._digest(schedule_raw)
            ):
                raise ValueError("history or schedule changed during authoring")
            if source is None:
                receipt["status"] = "abstained_not_admitted"
            else:
                envelope = templates[0]
                envelope.update(
                    operations=operations,
                    origin_refs=[row["origin_refs"][0] for row in templates],
                    cost=len(operations),
                    telegraph="next-use-v2-" + "".join(operations),
                    source=source.decode("utf-8"),
                    source_sha256=receipt["source_sha256"],
                )
                # C's JCS uses literal UTF-8, unlike ensure_ascii=True. All keys
                # here are fixed ASCII, and every numeric field is an integer.
                encoded = json.dumps(
                    envelope,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
                if len(encoded) > 8192:
                    raise ValueError("native envelope byte cap")
                # _publish may link the immutable target and then fail syncing.
                # Keep attempt identity even if neither durability nor readback
                # can be established; failure does not imply no publication.
                receipt["attempted_envelope_sha256"] = store._digest(encoded)
                store._publish(fd, _NAMES[3], encoded)
                if store._read(fd, _NAMES[3], 8192) != encoded:
                    raise ValueError("published envelope readback mismatch")
                receipt.update(
                    status="envelope_published_not_admitted",
                    envelope_sha256=store._digest(encoded),
                )
        except (ValueError, OSError, RuntimeError) as exc:
            receipt.update(
                status="publication_uncertain"
                if receipt["attempted_envelope_sha256"] is not None
                else "rejected_not_admitted",
                error_type=type(exc).__name__,
            )
            store._publish(fd, _NAMES[2], store._encode(receipt))
            raise
        encoded_receipt = store._encode(receipt)
        store._publish(fd, _NAMES[2], encoded_receipt)
        if store._read(fd, _NAMES[2], 8192) != encoded_receipt:
            raise ValueError("author receipt readback mismatch")
        return receipt
