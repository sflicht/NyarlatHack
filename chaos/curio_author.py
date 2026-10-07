"""Configured, history-grounded curio authoring and its run evidence (NGPL).

Proposal sections 3.2-3.5. One bounded authoring request for one game:

1. build_backend(config, ...) builds the configured transport. For xai and
   xai-oauth that is chaos.xai's ledgered XaiBackend; for openai-codex it is
   chaos.oauth's OAuthBackend with the curio purpose. Building an xai-oauth
   backend imports Hermes, which may re-exec the interpreter, so callers build
   it before any run state, ledger reservation or evidence exists.
2. author_curio(backend, ...) projects the checked native history with
   chaos.history.public_context, picks the literary layer from the game seed
   (curio.seeded_layer), composes the prompt (no cross-game continuity notes),
   sends within one 8-minute authoring deadline (at most two transport retries),
   parses the
   envelope, runs native validation (the engine's own admission calls plus a
   validation grid, chaos.curio_native) and then the prose truthfulness check
   (chaos.curio_truth). Every step is written to a fresh private evidence
   directory. Outcome "ready" is the only one install() accepts.
3. install(run_directory, evidence_dir, safe=...) publishes the logged source
   with curio_store.install_saved_source and records the safe point it was
   installed after, so a replay can install it at the same point
   (chaos.curio_replay). The engine's own admission stays the authority.

Evidence never holds a credential, header or key: transport receipts are
ledger rows (provider, model, route, hashes, status, latency, tokens).
"""

import hashlib
import json
import os
from pathlib import Path
import time

from . import curio, curio_store as store, curio_truth
from .history import public_context, snapshot_history

DEADLINE_S = 480  # Sam: raised to 8 minutes after the 368/391 s rerun responses
SURFACE = "curio"
OUTCOMES = (
    "transport_failed",
    "deadline",
    "envelope_rejected",
    "native_rejected",
    "truth_rejected",
    "ready",
)
_JSON_CAP = 262144


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _encode(value):
    return (_canonical(value) + "\n").encode("ascii")


def build_backend(config, *, ledger, run_id, client_factory=None, fresh_ledger=False):
    """The configured authoring backend, or None when nothing is configured.

    ledger is a chaos.xai.XaiLedger for xai/xai-oauth, or the openai-codex
    ledger path. Raises chaos.xai.NoModelReachable when an xAI provider is
    configured but unusable (no Hermes login, key variable unset).
    """
    if config is None:
        return None
    if config.provider in ("xai", "xai-oauth"):
        from . import xai

        return xai.build(
            config,
            ledger,
            run_id=run_id,
            surface=SURFACE,
            timeout=DEADLINE_S,
            client_factory=client_factory,
        )
    if config.provider == "openai-codex":
        from .oauth import CURIO_PURPOSE, OAuthBackend

        return OAuthBackend(
            ledger,
            model=config.model,
            purpose=CURIO_PURPOSE,
            client_factory=client_factory,
            fresh_ledger=fresh_ledger,
        )
    raise ValueError("unknown authoring provider")


def compose(events_dir, *, game_seed, role=None):
    """The exact prompt for a game, from checked native history only (rule 6)."""
    state, proof = snapshot_history(events_dir)
    history = public_context(state)
    public = {"sanity": state.latest["sanity"], "insight": state.latest["insight"]}
    if role is not None:
        public["role"] = role
    layer = curio.seeded_layer(game_seed)
    prompt = curio.compose_prompt(public, literary_layer=layer, history=history)
    return dict(
        v=1,
        game_seed=game_seed,
        layer=layer,
        public=public,
        history_event=proof["event"],
        public_context_sha256=_sha(_canonical(history).encode("ascii")),
        prompt_sha256=_sha((prompt.instructions + "\0" + prompt.prompt).encode()),
        instructions=prompt.instructions,
        prompt=prompt.prompt,
    )


def _new_directory(path):
    path = Path(path).absolute()
    with store._directory(path.parent) as parent:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        os.fsync(parent)
    return path


def author_curio(
    backend,
    *,
    events_dir,
    evidence_dir,
    game_seed,
    validator,
    role=None,
    deadline_s=DEADLINE_S,
    gate=None,
):
    """One authoring request; up to three ledgered sends within one deadline.

    Backends without an explicit retry hint are never retried. All known send
    receipts are retained in transport_attempts; no ledger cap is reset.

    gate, when given, is called as gate(outcome, fields, write) for the final
    receipt: the caller (the director's lane) decides under its own lock
    whether the outcome still stands, so a result its clock already gave up
    on is never written as ready.
    """
    if type(deadline_s) not in (int, float) or not 0 < deadline_s <= DEADLINE_S:
        raise ValueError("authoring deadline outside 0..480 seconds")
    started = time.monotonic()
    prepared = compose(events_dir, game_seed=game_seed, role=role)
    provider = getattr(getattr(backend, "config", None), "provider", None)
    if provider is None:
        provider = "openai-codex"
    model = getattr(getattr(backend, "config", None), "model", None) or backend.model
    evidence = _new_directory(evidence_dir)
    receipt = dict(
        v=1,
        provider=provider,
        model=model,
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
        truth_hits=None,
    )
    with store._directory(evidence) as d:
        store._publish(d, "prompt.json", _encode(prepared))

        def write(outcome, fields):
            receipt.update(fields, outcome=outcome)
            store._publish(d, "receipt.json", _encode(receipt))
            return dict(receipt)

        def finish(outcome, **fields):
            if gate is None:
                return write(outcome, fields)
            return gate(outcome, fields, write)

        backend.deadline = started + deadline_s
        attempts = []
        for attempt in range(3):
            # A backend must opt in after a known-durable transport failure;
            # never retry arbitrary validation, credential or ledger errors.
            backend.retry_delay = None
            try:
                raw, transport = backend.generate(
                    prepared["instructions"], prepared["prompt"], return_receipt=True
                )
                attempts.append(transport)
                break
            except Exception as exc:
                transport = getattr(backend, "last_receipt", None)
                attempts.append(transport)
                delay = getattr(backend, "retry_delay", None)
                remaining = backend.deadline - time.monotonic()
                timed_out = isinstance(exc, TimeoutError) or remaining <= 0
                if (
                    not timed_out
                    and attempt < 2
                    and delay is not None
                    and delay >= 0
                    and delay < remaining
                ):
                    time.sleep(delay)
                    continue
                return finish(
                    "deadline" if timed_out else "transport_failed",
                    error_type=type(exc).__name__[:80],
                    latency_s=round(time.monotonic() - started, 3),
                    transport=transport,
                    transport_attempts=attempts,
                )
        receipt["transport_attempts"] = attempts
        arrived = time.monotonic()
        raw_bytes = raw.encode("utf-8")
        store._publish(d, "raw-response.txt", raw_bytes)
        receipt.update(
            latency_s=round(arrived - started, 3),
            transport=transport,
            raw_response_sha256=_sha(raw_bytes),
        )
        # The transport's timeout bounds each socket wait, not the whole
        # response, so a slow stream can finish late. Late is never installed.
        if arrived > started + deadline_s:
            return finish("deadline", error_type="LateResponse")
        try:
            envelope = curio.parse_envelope(raw)
        except ValueError:
            return finish("envelope_rejected", error_type="ValueError")
        store._publish(d, "source.lua", envelope.lua_source)
        receipt["lua_source_sha256"] = _sha(envelope.lua_source)
        public = prepared["public"]
        native = validator.validate(
            envelope.lua_source, public["sanity"], public["insight"]
        )
        native["library_sha256"] = validator.library_sha256
        receipt["native"] = native
        if not native["admitted"]:
            return finish("native_rejected")
        hits = curio_truth.check(curio_truth.curio_texts(native))
        if time.monotonic() > started + deadline_s:
            return finish("deadline", error_type="LateValidation", truth_hits=hits)
        return finish("truth_rejected" if hits else "ready", truth_hits=hits)


def _read_json(directory, name):
    raw = store._read(directory, name, _JSON_CAP)
    value = json.loads(raw)
    if raw != _encode(value):
        raise ValueError(f"noncanonical {name}")
    return value


def read_evidence(evidence_dir):
    """Verify a ready evidence directory read-only; return its receipt.

    Checks the hash chain prompt -> raw response -> envelope -> source, the
    seeded layer, and the outcome. Never contacts a model.
    """
    with store._directory(evidence_dir) as d:
        prepared = _read_json(d, "prompt.json")
        receipt = _read_json(d, "receipt.json")
        if receipt["outcome"] != "ready":
            raise ValueError("only a ready curio can be installed or replayed")
        raw = store._read(d, "raw-response.txt", curio.MAX_RESPONSE_BYTES)
        source = store._read(d, "source.lua", curio.MAX_SOURCE_BYTES)
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
        or curio.parse_envelope(raw.decode("utf-8")).lua_source != source
        or _sha(source) != receipt["lua_source_sha256"]
    ):
        raise ValueError("curio evidence hash chain does not verify")
    return receipt


def install(run_directory, evidence_dir, *, safe):
    """Publish a ready curio into a run directory and record the safe point.

    safe is the run's latest safe-point index when the source is published;
    the engine reads it at the next safe point. Standalone, like
    curio_store.install_saved_source: a running director instead installs
    under its own held lock (slice 3).
    """
    if type(safe) is not int or safe < 0:
        raise ValueError("safe point index must be a nonnegative integer")
    receipt = read_evidence(evidence_dir)
    with store._directory(evidence_dir) as d:
        if store._exists(d, "install.json"):
            raise ValueError("curio evidence already installed")
    result = store.install_saved_source(
        run_directory, source_file=Path(evidence_dir) / "source.lua"
    )
    if result["source_sha256"] != receipt["lua_source_sha256"]:
        raise ValueError("installed source differs from the evidence")
    record = dict(v=1, safe=safe, source_sha256=result["source_sha256"])
    with store._directory(evidence_dir) as d:
        store._publish(d, "install.json", _encode(record))
    return record


def read_install(evidence_dir):
    with store._directory(evidence_dir) as d:
        record = _read_json(d, "install.json")
    if set(record) != {"v", "safe", "source_sha256"} or record["v"] != 1:
        raise ValueError("invalid install record")
    if type(record["safe"]) is not int or record["safe"] < 0:
        raise ValueError("invalid install safe point")
    return record
