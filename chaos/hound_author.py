"""Model-authored hound: one free-design pursuit per game (NGPL; slice 5a).

Proposal section 4 "Hound". The prescribed program in the old haunting.txt
left the model nothing to author; the prompt now asks it to design the
pursuit from this game's public history (rule 6) and keep it learnable and
escapable. Every contract line stays: the c-table fields and return shape,
the source bound, no libraries, engine-validated moves, and the engine's own
shadow trial, which stays the authority.

1. build_backend(config, ...) builds the ledgered xAI backend for surface
   "haunt" (xai or xai-oauth only; anything else has no model hound and keeps
   footsteps.lua). Building may os.execv into Hermes, so callers build it
   before any run state.
2. author_hound(backend, ...) projects the checked native history with
   chaos.history.public_context, adds the seeded literary layer, sends within
   one deadline, parses the {"source": ...} envelope, and runs the host
   pre-check (HoundValidator: the engine's own chaos_lua_step over a fixed
   grid of trails). Every step is written to a fresh private evidence
   directory; "ready" is the only outcome the lane publishes.

Evidence never holds a credential, header or key: transport receipts are
ledger rows (provider, model, route, hashes, status, latency, tokens).
"""

import ctypes
import hashlib
import json
from pathlib import Path
import time

from . import curio, curio_store as store, lane
from .curio_author import _canonical, _encode, _new_directory, _read_json, _sha
from .history import public_context, snapshot_history

DEADLINE_S = 480  # the curio lane's authoring deadline (Sam, slice 3a)
SURFACE = "haunt"
PROVIDERS = ("xai", "xai-oauth")
MAX_SOURCE_BYTES = 4096  # CHAOS_LUA_SOURCE
MAX_RESPONSE_BYTES = 8192
MAX_PROMPT_BYTES = curio.MAX_PROMPT_BYTES
OUTCOMES = (
    "transport_failed",
    "deadline",
    "envelope_rejected",
    "native_rejected",
    "ready",
)
_PROMPTS = Path(__file__).resolve().parent / "prompts"


def build_backend(config, *, ledger, run_id, client_factory=None):
    """The hound's ledgered backend, or None when no xAI provider is
    configured (then the hound stays footsteps.lua). Raises
    chaos.xai.NoModelReachable when the provider is configured but unusable."""
    if config is None or config.provider not in PROVIDERS:
        return None
    from . import xai

    return xai.build(
        config,
        ledger,
        run_id=run_id,
        surface=SURFACE,
        timeout=DEADLINE_S,
        client_factory=client_factory,
    )


def compose_prompt(history, *, literary_layer):
    """Trusted prompt files + the quoted public history; never call a model."""
    if literary_layer not in curio.LAYERS:
        raise ValueError("unknown literary layer")
    names = [
        _PROMPTS / "haunting.txt",
        _PROMPTS / "hound" / "literary.txt",
        _PROMPTS / "curio" / curio._LITERARY_FILES[literary_layer],
    ]
    instructions = "\n\n".join(p.read_text(encoding="utf-8") for p in names)
    prompt = json.dumps(
        {"public_history": curio._history(history)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len((instructions + prompt).encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("combined prompt byte cap exceeded")
    return instructions, prompt


def compose(events_dir, *, game_seed):
    """The exact prompt for a game, from checked native history only (rule 6)."""
    state, proof = snapshot_history(events_dir)
    return prepare(public_context(state), game_seed=game_seed, event=proof["event"])


def prepare(history, *, game_seed, event):
    """The prompt record for an allowlisted public history (public_context)."""
    layer = curio.seeded_layer(game_seed)
    instructions, prompt = compose_prompt(history, literary_layer=layer)
    return dict(
        v=1,
        game_seed=game_seed,
        layer=layer,
        history_event=event,
        public_context_sha256=_sha(_canonical(history).encode("ascii")),
        prompt_sha256=_sha((instructions + "\0" + prompt).encode()),
        instructions=instructions,
        prompt=prompt,
    )


def parse_envelope(raw_response):
    """Exactly {"source": "<1..4096 bytes, no NUL>"}; the exact Lua bytes."""
    if len(raw_response.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("response byte cap exceeded")
    try:
        obj = json.loads(
            raw_response,
            object_pairs_hook=curio._unique_object,
            parse_constant=curio._reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("authoring response must be one JSON object") from exc
    if (
        type(obj) is not dict
        or set(obj) != {"source"}
        or type(obj["source"]) is not str
    ):
        raise ValueError("hound envelope requires exactly one string field source")
    source = obj["source"].encode("utf-8")
    if not 0 < len(source) <= MAX_SOURCE_BYTES or b"\0" in source:
        raise ValueError("source bounds violated")
    return source


# ---------------------------------------------------------------- pre-check
class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int)]


class _StepContext(ctypes.Structure):
    _fields_ = [
        ("mx", ctypes.c_int),
        ("my", ctypes.c_int),
        ("state", ctypes.c_int),
        ("count", ctypes.c_int),
        ("history", _Point * 8),
    ]


class _StepIntent(ctypes.Structure):
    _fields_ = [(k, ctypes.c_int) for k in ("dx", "dy", "state")]


# Trails the hound can meet (oldest first): straight, doubling back, a turn,
# standing still; short and full; from behind and from ahead; four states.
_SHAPES = (
    tuple((10 + i, 5) for i in range(8)),
    tuple((20 - i, 8) for i in range(8)),
    ((12, 4), (13, 4), (14, 4), (15, 4), (14, 4), (13, 4), (12, 4), (11, 4)),
    ((30, 10), (31, 11), (32, 12), (33, 12), (33, 11), (33, 10), (32, 9), (31, 9)),
    ((5, 5),) * 8,
)
GRID = tuple(
    (mx, my, state, shape[:count])
    for shape in _SHAPES
    for count in (1, 4, 8)
    for mx, my in (
        (shape[0][0] - 3, shape[0][1]),
        (shape[-1][0] + 2, shape[-1][1] + 2),
    )
    for state in (0, 1, 7, 999999)
)


# Pressure floor (Sam, 2026-10-07: "Make hounds hunt"; placement: orchestrator
# option A). Pre-registered in docs/measurements/hound-hunting/README.md
# before any new generation. The shadow trial's 64-step rehearsal, replayed
# offline: the same evasive bot, the same hound placement, the same scripted
# step rules (chaos_haunt_pick: plain floor, never the player's square, the
# #190 nearer-candidate fallback) in three bare lit rooms. No RNG is involved,
# so each room is one deterministic rehearsal. Damage and death are not
# modelled; the engine's own shadow trial keeps those bounds.
REHEARSAL_ROOMS = (  # W, H, player offset X, Y (the pilot's bare rooms)
    ("bare-6x4", 6, 4, 2, 1),
    ("bare-12x6", 12, 6, 5, 3),
    ("bare-20x8", 20, 8, 10, 4),
)
REHEARSAL_STEPS = 64
MIN_MOVED = 16  # moves on at least 25 % of steps
CONTACT = 1  # comes within 1 square (Chebyshev) at least once
ESCAPE = 3  # the player gets 3 squares away after step 9 (engine rule)
_X0, _Y0 = 20, 5  # room origin, as in tests/chaos/haunt_room.c
_BOT = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))


def _cheb(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


def _d2(ax, ay, bx, by):
    return (ax - bx) ** 2 + (ay - by) ** 2


class HoundValidator:
    """Host pre-check through the engine's own per-decision call.

    chaos_lua_step (src/chaos_lua.c, the call chaos_haunt_pick makes for
    every hound decision) from the native validator library the launcher
    already loads (curio-validator.so, built from the unmodified engine
    source). A candidate passes when every grid decision returns a valid
    intent and it moves in at least one. Passing is not admission: the
    engine's shadow trial re-checks the exact bytes against an evasive
    player in a sealed copy of the real level.
    """

    def __init__(self, library):
        path = Path(library)
        if not path.is_absolute():
            raise ValueError("explicit absolute trusted native library required")
        self.library_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self._step = ctypes.CDLL(str(path)).chaos_lua_step
        self._step.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(_StepContext),
            ctypes.POINTER(_StepIntent),
        ]
        self._step.restype = ctypes.c_int

    def validate(self, source):
        if type(source) is not bytes or not 0 < len(source) <= MAX_SOURCE_BYTES:
            raise ValueError("source bytes outside 1..4096")
        failures = moved = 0
        intents = set()
        for mx, my, state, trail in GRID:
            c = _StepContext(mx, my, state, len(trail))
            for i, (x, y) in enumerate(trail):
                c.history[i] = _Point(x, y)
            out = _StepIntent()
            if self._step(source, len(source), ctypes.byref(c), ctypes.byref(out)):
                failures += 1
                continue
            intents.add((out.dx, out.dy))
            moved += bool(out.dx or out.dy)
        failure = "native_step" if failures else "never_moves" if not moved else None
        rehearsal = []
        if failure is None:
            rehearsal = [self.rehearse(source, room) for room in REHEARSAL_ROOMS]
            failure = next((r["failure"] for r in rehearsal if r["failure"]), None)
        return dict(
            admitted=failure is None,
            failure=failure,
            grid_calls=len(GRID),
            grid_failures=failures,
            grid_moves=moved,
            distinct_steps=len(intents),
            rehearsal=rehearsal,
            library_sha256=self.library_sha256,
        )

    def _intent(self, source, mx, my, state, trail):
        c = _StepContext(mx, my, state, len(trail))
        for i, (x, y) in enumerate(trail):
            c.history[i] = _Point(x, y)
        out = _StepIntent()
        if self._step(source, len(source), ctypes.byref(c), ctypes.byref(out)):
            return None
        return out.dx, out.dy, out.state

    def rehearse(self, source, room):
        """One 64-step rehearsal in a bare room; the pressure floor's verdict.

        Mirrors chaos_haunt.c trial(): the bot steps first (the legal square
        farthest from the hound, scanning directions from a rotating start),
        the player's square joins the trail, then the hound takes one scripted
        step, then distance is measured. Failures, in order: script_error,
        barely_moves (moved < MIN_MOVED), never_closes (never within CONTACT),
        cornered (the player never got ESCAPE squares away after step 9)."""
        name, w, h, px, py = room

        def floor(x, y):
            return _X0 <= x < _X0 + w and _Y0 <= y < _Y0 + h

        ux, uy = _X0 + px, _Y0 + py
        # chaos_haunt_tick: the first floor square, rows then columns, within
        # 5 of the player and at least 3 away.
        mx = my = None
        for y in range(uy - 5, uy + 6):
            for x in range(ux - 5, ux + 6):
                if mx is None and floor(x, y) and _cheb(x, y, ux, uy) >= ESCAPE:
                    mx, my = x, y
        if mx is None or my is None:
            raise ValueError("rehearsal room has no hound square")
        trail = [(ux, uy)] * 4
        state = moved = contacts = steps = errors = 0
        dists, escaped = [], False
        for i in range(REHEARSAL_STEPS):
            best, bx, by = -1, ux, uy
            for j in range(8):
                dx, dy = _BOT[(j + i) % 8]
                nx, ny = ux + dx, uy + dy
                if floor(nx, ny) and (nx, ny) != (mx, my):
                    score = _d2(nx, ny, mx, my)
                    if score > best:
                        best, bx, by = score, nx, ny
            ux, uy = bx, by
            trail = (trail + [(ux, uy)])[-8:]
            intent = self._intent(source, mx, my, state, trail)
            steps += 1
            if intent is None:
                errors += 1
                break
            dx, dy, new_state = intent
            if not dx and not dy:
                state = new_state
            else:
                tx, ty = mx + dx, my + dy
                # mfndpos order: x ascending, then y; legal_step: floor, empty,
                # not the player.
                cands = [
                    (x, y)
                    for x in range(mx - 1, mx + 2)
                    for y in range(my - 1, my + 2)
                    if (x, y) != (mx, my) and floor(x, y) and (x, y) != (ux, uy)
                ]
                dest = (tx, ty) if (tx, ty) in cands else None
                if dest is None and (tx, ty) != (ux, uy):
                    far = _cheb(tx, ty, ux, uy) > 1
                    bd = _d2(mx, my, tx, ty)
                    for x, y in cands:
                        if far and _cheb(x, y, ux, uy) <= 1:
                            continue
                        d = _d2(x, y, tx, ty)
                        if d < bd:
                            bd, dest = d, (x, y)
                if dest is not None:
                    mx, my = dest
                    state = new_state
                    moved += 1
            d = _cheb(mx, my, ux, uy)
            dists.append(d)
            contacts += d <= CONTACT
            if i > 8 and d >= ESCAPE:
                escaped = True
        failure = (
            "script_error"
            if errors
            else "barely_moves"
            if moved < MIN_MOVED
            else "never_closes"
            if not contacts
            else "cornered"
            if not escaped
            else None
        )
        return dict(
            room=name,
            steps=steps,
            moved=moved,
            contacts=contacts,
            min_dist=min(dists) if dists else None,
            median_dist=sorted(dists)[(len(dists) - 1) // 2] if dists else None,
            escaped=int(escaped),
            failure=failure,
        )


# ---------------------------------------------------------------- authoring
def author_hound(
    backend,
    *,
    events_dir,
    evidence_dir,
    game_seed,
    validator,
    deadline_s=DEADLINE_S,
    gate=None,
    prepared=None,
):
    """One authoring request into a fresh evidence directory.

    gate, when given, is the lane's gate(outcome, fields, write) for the final
    receipt (late results become the lane's deadline failure). prepared (the
    offline pilot only) replaces compose(events_dir) with a prompt composed
    from a recorded public history."""
    if type(deadline_s) not in (int, float) or not 0 < deadline_s <= DEADLINE_S:
        raise ValueError("authoring deadline outside 0..480 seconds")
    started = time.monotonic()
    if prepared is None:
        prepared = compose(events_dir, game_seed=game_seed)
    evidence = _new_directory(evidence_dir)
    receipt = dict(
        v=1,
        surface=SURFACE,
        provider=backend.config.provider,
        model=backend.config.model,
        layer=prepared["layer"],
        game_seed=game_seed,
        prompt_sha256=prepared["prompt_sha256"],
        public_context_sha256=prepared["public_context_sha256"],
        history_event=prepared["history_event"],
        deadline_s=deadline_s,
        outcome=None,
        error_type=None,
        latency_s=None,
        transport=None,
        raw_response_sha256=None,
        lua_source_sha256=None,
        native=None,
    )
    with store._directory(evidence) as d:
        store._publish(d, "prompt.json", _encode(prepared))

        def write(outcome, fields):
            receipt.update(fields, outcome=outcome)
            store._publish(d, "receipt.json", _encode(receipt))
            return dict(receipt)

        def finish(outcome, **fields):
            return (
                write(outcome, fields) if gate is None else gate(outcome, fields, write)
            )

        try:
            raw, transport, attempts = lane.send(
                backend,
                prepared["instructions"],
                prepared["prompt"],
                started=started,
                deadline_s=deadline_s,
            )
        except lane.SendFailed as failed:
            return finish(failed.outcome, **failed.fields)
        receipt["transport_attempts"] = attempts
        arrived = time.monotonic()
        raw_bytes = raw.encode("utf-8")
        store._publish(d, "raw-response.txt", raw_bytes)
        receipt.update(
            latency_s=round(arrived - started, 3),
            transport=transport,
            raw_response_sha256=_sha(raw_bytes),
        )
        if arrived > started + deadline_s:
            return finish("deadline", error_type="LateResponse")
        try:
            source = parse_envelope(raw)
        except ValueError:
            return finish("envelope_rejected", error_type="ValueError")
        store._publish(d, "source.lua", source)
        receipt["lua_source_sha256"] = _sha(source)
        native = validator.validate(source)
        receipt["native"] = native
        if not native["admitted"]:
            return finish("native_rejected")
        if time.monotonic() > started + deadline_s:
            return finish("deadline", error_type="LateValidation")
        return finish("ready")


def read_evidence(evidence_dir):
    """Verify a ready evidence directory read-only; return its receipt.

    Checks the hash chain prompt -> raw response -> envelope -> source and the
    seeded layer. Never contacts a model."""
    with store._directory(evidence_dir) as d:
        prepared = _read_json(d, "prompt.json")
        receipt = _read_json(d, "receipt.json")
        if receipt["outcome"] != "ready":
            raise ValueError("only a ready hound can be published or replayed")
        raw = store._read(d, "raw-response.txt", MAX_RESPONSE_BYTES)
        source = store._read(d, "source.lua", MAX_SOURCE_BYTES)
    joined = (prepared["instructions"] + "\0" + prepared["prompt"]).encode()
    history = json.loads(prepared["prompt"]).get("public_history")
    if (
        _sha(joined) != prepared["prompt_sha256"]
        or prepared["prompt_sha256"] != receipt["prompt_sha256"]
        or prepared["layer"] != curio.seeded_layer(prepared["game_seed"])
        or prepared["layer"] != receipt["layer"]
        or history is None
        or _sha(_canonical(history).encode("ascii")) != receipt["public_context_sha256"]
        or _sha(raw) != receipt["raw_response_sha256"]
        or parse_envelope(raw.decode("utf-8")) != source
        or _sha(source) != receipt["lua_source_sha256"]
    ):
        raise ValueError("hound evidence hash chain does not verify")
    return receipt
