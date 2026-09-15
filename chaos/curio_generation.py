"""One explicit bounded authoring attempt, never installation or native validation.

NGPL. generate_curio requires stable offline native history, private host paths,
a verified continuity journal and the retained shared OAuth ledger (fresh_ledger
is explicit initialization for temporary tests, never reset). Optional role/race
are host assertions, NOT discovered from arbitrary event extras. Only sanity and
insight are projected from events. No credentials are opened during preflight.

Publication: exclusive output directory; durable prepared.json before reservation
and factory; one pinned request; exact raw-response.json before envelope parsing;
store exact candidate, register, publish generation.json then complete.commit.
Failures keep published partial evidence, spend any reservation, and never retry,
refund, repair or install. failure.json contains the stage, exception TYPE (never
its message), reservation-attempted flag and bounded last-known transport metadata
(possibly None or a stale reserved receipt); it never rereads uncertain ledgers.
It is best effort and cannot certify durability. An unregistered stored candidate
blocks later generation until manual reconciliation. Existing output always fails.

read_generation verifies immutable context prefix/inode, original trusted prompt,
all current journal/bundle evidence, historical notes and exact registration, raw
and source bytes, and the actual indexed authorization record. It performs no
creation, fsync, inference or recovery. Complete bytes are evidence, not proof that
a previously failed sync succeeded. Paths and hashes are host evidence, not a
cryptographic signature or proof of live authorship: injected clients are allowed.

Cooperating offline writers/private owned local resources are the trust boundary.
Rechecks detect ordinary drift before/after factory and request, but do not freeze
a playing engine, malicious same-UID ABA rewrites or filesystem snapshots. Later
inspection permits valid append-only native history and journal advancement.
"""

import os
from pathlib import Path

from . import curio, curio_continuity as continuity, curio_store as store
from .director import State
from .oauth import CURIO_PURPOSE, OAuthBackend, native_client
from .protocol import parse_event, strict_json

_METADATA_CAP = 65536
_COMPLETE_FILES = {
    "prepared.json",
    "raw-response.json",
    "generation.json",
    "complete.commit",
}


def _equal(actual, expected):
    # Canonical JSON comparison also rejects bool-for-int and extra schema keys.
    if store._encode(actual) != store._encode(expected):
        raise ValueError("generation evidence binding changed")


def _project(raw):
    if not raw or not raw.endswith(b"\n"):
        raise ValueError("complete nonempty native history required")
    lines = raw.split(b"\n")[:-1]
    if len(lines) > continuity.MAX_EVENTS:
        raise ValueError("event count cap exceeded")
    state = State()
    for index, line in enumerate(lines):
        try:
            e = parse_event(line.decode("utf-8"))
            if len(line) > 4096 or e["seq"] != index + 1:
                raise ValueError("event line cap or sequence gap")
            if index == 0 and (e["event"], e["phase"], e["detail"]) != (
                "session",
                "result",
                "new",
            ):
                raise ValueError("full new-session history required")
            if e["event"] == "session":
                if e["phase"] != "result" or e["detail"] != (
                    "restore" if index else "new"
                ):
                    raise ValueError("conflicting session chain")
                if not index and any(
                    e[k] for k in ("safe", "spent", "reserved", "last_id")
                ):
                    raise ValueError("invalid fresh counters")
            curio._public_context({k: e[k] for k in ("sanity", "insight")})
            state.ingest(e)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid native history") from exc
    return {k: state.latest[k] for k in ("sanity", "insight")}


def _context(path, *, checkpoint=None, fresh=False):
    path = Path(path)
    with store._directory(path.parent) as d:
        if fresh:
            store._check_names(d)
            if any(store._exists(d, name) for name in store._INSTALL_FILES):
                raise ValueError("existing native candidate evidence")
        raw, proof = continuity._file(d, path.name, continuity.MAX_EVENT_BYTES)
        public = _project(raw)
        if checkpoint is not None:
            length = checkpoint["event"]["length"]
            if type(length) is not int or not 1 <= length <= len(raw):
                raise ValueError("invalid context prefix length")
            raw = raw[:length]
            proof = dict(proof, length=length, sha256=store._digest(raw))
            public = _project(raw)
        evidence = dict(directory=continuity._inode(os.fstat(d)), event=proof)
    if checkpoint is not None:
        _equal(evidence, checkpoint)
    return public, evidence


def _journal(journal_root, bundle_root, *, checkpoint=None, room=False):
    """Verify ALL current evidence, derive notes at a bound historical prefix."""
    with store._directory(journal_root) as d, store._writer_lock(d, create=False):
        latest, current, total, head = continuity._load(d)
        if room and total >= continuity.MAX_RECORDS:
            raise ValueError("no continuity registration slot")
        with store._directory(bundle_root) as b:
            names = set()
            with os.scandir(b) as entries:
                for entry in entries:
                    if len(names) >= continuity.MAX_RECORDS:
                        raise ValueError("bundle count cap exceeded")
                    identity = store._identity(entry.name)
                    store.read_candidate(bundle_root, identity)
                    names.add(identity)
            registered = {
                i for i, r in latest.items() if r["bundle_root"] == bundle_root
            }
            if names != registered:
                raise ValueError(
                    "unregistered or missing bundle; manual reconciliation required"
                )
            bundle_identity = continuity._inode(os.fstat(b))
        count = total if checkpoint is None else checkpoint["count"]
        if type(count) is not int or not 0 <= count <= total:
            raise ValueError("invalid continuity prefix")
        historical = {}
        head = "0" * 64
        for i in range(1, count + 1):
            raw = store._read(d, f"{i:06d}.json", continuity.MAX_RECORD_BYTES)
            record = strict_json(raw.decode("utf-8"), continuity.MAX_RECORD_BYTES)
            historical[record["candidate_id"]] = record
            head = store._digest(raw)
        notes = []
        for identity in list(historical)[-curio.MAX_PRIOR_NOTES :]:
            r = historical[identity]
            candidate, _, events, _ = current[identity]
            run = r["proof"]["run"]
            status = "authored"
            if run is not None:
                length = run["event"]["length"] if run["event"] else 0
                status = continuity._lifecycle(
                    events[:length], "curio-used.lua" in run["files"]
                )
            notes.append(
                dict(
                    candidate_id=identity,
                    status=status,
                    continuity_note=candidate.continuity_note,
                )
            )
        evidence = dict(
            directory=continuity._inode(os.fstat(d)),
            bundle_directory=bundle_identity,
            count=count,
            head=head,
            notes=notes,
        )
    if checkpoint is not None:
        _equal(evidence, checkpoint)
    return evidence


def _prepared(paths, literary_layer, host, *, context=None, journal=None, fresh=False):
    public, context = _context(paths["event_file"], checkpoint=context, fresh=fresh)
    if type(host) is not dict or not host.keys() <= {"role", "race"}:
        raise ValueError("only optional host role/race permitted")
    public.update(host)
    journal = _journal(
        paths["journal_root"], paths["bundle_root"], checkpoint=journal, room=fresh
    )
    prompt = curio.compose_prompt(
        public, prior_notes=journal["notes"], literary_layer=literary_layer
    )
    prepared = dict(
        version=1,
        paths=paths,
        literary_layer=literary_layer,
        host=host,
        context=context,
        journal=journal,
        public_context=public,
        instructions=prompt.instructions,
        prompt=prompt.prompt,
    )
    _metadata(prepared)
    return prepared


def _metadata(value):
    raw = store._encode(value)
    if len(raw) > _METADATA_CAP:
        raise ValueError("generation metadata cap exceeded")
    return raw


def _registration(prepared, candidate_id):
    paths = prepared["paths"]
    with (
        store._directory(paths["journal_root"]) as d,
        store._writer_lock(d, create=False),
    ):
        continuity._load(d)
        seq = prepared["journal"]["count"] + 1
        raw = store._read(d, f"{seq:06d}.json", continuity.MAX_RECORD_BYTES)
        record = strict_json(raw.decode("utf-8"), continuity.MAX_RECORD_BYTES)
        candidate = store.read_candidate(paths["bundle_root"], candidate_id)
        expected = dict(
            version=1,
            seq=seq,
            previous=prepared["journal"]["head"],
            op="register",
            candidate_id=candidate_id,
            bundle_root=paths["bundle_root"],
            run=None,
            proof=dict(
                raw_sha256=store._digest(candidate.raw_response.encode()), run=None
            ),
        )
        _equal(record, expected)
        return dict(seq=seq, sha256=store._digest(raw))


def _receipt(prepared, raw, transport):
    envelope = curio.parse_envelope(raw.decode("utf-8"))
    identity = store._digest(envelope.lua_source)
    candidate = store.read_candidate(prepared["paths"]["bundle_root"], identity)
    if (
        candidate.raw_response.encode() != raw
        or candidate.lua_source != envelope.lua_source
    ):
        raise ValueError("candidate differs from exact backend output")
    backend = OAuthBackend(prepared["paths"]["ledger"], purpose=CURIO_PURPOSE)
    actual = backend.receipt(transport["record_index"])
    _equal(transport, actual)
    record = actual["record"]
    if (
        record["status"] != "completed"
        or record.get("purpose") != CURIO_PURPOSE
        or record["prompt_sha256"]
        != store._digest(
            (prepared["instructions"] + "\0" + prepared["prompt"]).encode()
        )
    ):
        raise ValueError("transport does not bind this authoring attempt")
    return dict(
        version=1,
        status="candidate_stored_registered_not_installed",
        provenance="pinned_oauth_backend_response_not_live_attestation",
        prepared_sha256=store._digest(_metadata(prepared)),
        source_sha256=identity,
        raw_response_sha256=store._digest(raw),
        transport=actual,
        registration=_registration(prepared, identity),
    )


def _read_generation(directory):
    if continuity._names(directory) != _COMPLETE_FILES:
        raise ValueError("incomplete or unknown generation evidence")
    prepared_raw = store._read(directory, "prepared.json", _METADATA_CAP)
    prepared = strict_json(prepared_raw.decode("utf-8"), _METADATA_CAP)
    try:
        paths = prepared["paths"]
        if type(paths) is not dict or paths.keys() != {
            "event_file",
            "bundle_root",
            "journal_root",
            "ledger",
        }:
            raise ValueError("invalid generation paths")
        for value in paths.values():
            if type(value) is not str or continuity._path(value) != value:
                raise ValueError("invalid persisted host path")
        expected = _prepared(
            paths,
            prepared["literary_layer"],
            prepared["host"],
            context=prepared["context"],
            journal=prepared["journal"],
        )
        _equal(prepared, expected)
        if prepared_raw != _metadata(expected):
            raise ValueError("noncanonical prepared evidence")
        raw = store._read(directory, "raw-response.json", curio.MAX_RESPONSE_BYTES)
        receipt_raw = store._read(directory, "generation.json", _METADATA_CAP)
        receipt = strict_json(receipt_raw.decode("utf-8"), _METADATA_CAP)
        expected_receipt = _receipt(expected, raw, receipt["transport"])
        _equal(receipt, expected_receipt)
        if receipt_raw != _metadata(expected_receipt):
            raise ValueError("noncanonical generation receipt")
        if (
            store._read(directory, "complete.commit", 64)
            != store._digest(receipt_raw).encode()
        ):
            raise ValueError("invalid generation commit")
        return receipt
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError("invalid generation metadata schema") from exc


def read_generation(output_directory):
    """Read-only complete evidence verification; never retry/recover a failure."""
    with store._directory(output_directory) as d:
        return _read_generation(d)


def generate_curio(
    *,
    event_file,
    output_directory,
    bundle_root,
    journal_root,
    ledger,
    literary_layer="poe",
    role=None,
    race=None,
    fresh_ledger=False,
    client_factory=native_client,
):
    """One explicit attempt. No installation, implicit ledger reset or retries."""
    paths = {
        k: continuity._path(v)
        for k, v in dict(
            event_file=event_file,
            bundle_root=bundle_root,
            journal_root=journal_root,
            ledger=ledger,
        ).items()
    }
    output = Path(continuity._path(output_directory))
    # Publishing into a managed evidence tree would itself invalidate preflight.
    # Reject known topology conflicts before output or authorization reservation.
    managed = [Path(paths[k]) for k in ("bundle_root", "journal_root")]
    managed.append(Path(paths["event_file"]).parent)
    for root in managed:
        if (
            output.is_relative_to(root)
            or root.is_relative_to(output)
            or Path(paths["ledger"]).is_relative_to(root)
        ):
            raise ValueError(
                "generation output/ledger must be outside managed evidence trees"
            )
    ledger_path = Path(paths["ledger"])
    if (
        ledger_path.is_relative_to(output)
        or output == Path(str(ledger_path) + ".lock")
        or output.name.startswith(".oauth-ledger-")
    ):
        raise ValueError("generation output conflicts with authorization evidence")
    with store._directory(output.parent) as parent:
        if store._exists(parent, output.name):
            raise ValueError("fresh output directory required")
    host = {k: v for k, v in dict(role=role, race=race).items() if v is not None}
    prepared = _prepared(paths, literary_layer, host, fresh=True)

    def stable():
        _equal(_prepared(paths, literary_layer, host, fresh=True), prepared)

    def factory():
        stable()
        client, model = client_factory()
        try:
            stable()
        except Exception:
            if client is not None:
                client.close()
            raise
        return client, model

    backend = OAuthBackend(
        paths["ledger"],
        purpose=CURIO_PURPOSE,
        fresh_ledger=fresh_ledger,
        client_factory=factory,
    )
    backend.preflight()
    # All read-only preflight is complete before even reserving output.
    with store._directory(output.parent) as parent:
        os.mkdir(output.name, 0o700, dir_fd=parent)
        os.fsync(parent)
        with store._bundle_directory(parent, output.name) as d:
            stage = "prepared"
            try:
                store._publish(d, "prepared.json", _metadata(prepared))
                if store._read(d, "prepared.json", _METADATA_CAP) != _metadata(
                    prepared
                ):
                    raise ValueError("prepared readback mismatch")
                stage = "transport"
                raw, transport = backend.generate(
                    prepared["instructions"], prepared["prompt"], return_receipt=True
                )
                stage = "raw_response"
                store._publish(d, "raw-response.json", raw.encode("utf-8"))
                if store._read(
                    d, "raw-response.json", curio.MAX_RESPONSE_BYTES
                ) != raw.encode("utf-8"):
                    raise ValueError("raw response readback mismatch")
                stage = "envelope"
                curio.parse_envelope(raw)
                stage = "context_recheck"
                stable()
                stage = "store"
                candidate = store.store_candidate(paths["bundle_root"], raw)
                stage = "register"
                continuity.register(
                    paths["journal_root"], paths["bundle_root"], candidate.candidate_id
                )
                stage = "receipt"
                receipt = _receipt(prepared, raw.encode("utf-8"), transport)
                store._publish(d, "generation.json", _metadata(receipt))
                store._publish(
                    d, "complete.commit", store._digest(_metadata(receipt)).encode()
                )
                stage = "readback"
                return _read_generation(d)
            except Exception as exc:
                try:
                    store._publish(
                        d,
                        "failure.json",
                        _metadata(
                            dict(
                                version=1,
                                stage=stage,
                                error_type=type(exc).__name__[:80],
                                reservation_attempted=backend.reservation_attempted,
                                last_known_transport=backend.last_receipt,
                            )
                        ),
                    )
                except (OSError, ValueError):
                    pass  # Never mask the primary error or erase published evidence.
                raise
