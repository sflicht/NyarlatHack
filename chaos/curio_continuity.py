"""Bounded offline continuity evidence, not model authorship or game control. NGPL.

Explicit create_journal requires an empty private root. register binds a verified
bundle; bind_run binds one installation once; observe checkpoints native evidence.
prior_notes is read-only and refuses uncheckpointed evidence. All history is
revalidated before selecting the latest distinct registrations (oldest first).

Version 1: exclusive 000001.json records plus matching .commit digest checkpoints,
with sequence and predecessor hash. No mutable counters, clocks, repair or retry.
An incomplete pair fails closed. Complete bytes after a failed fsync are evidence,
NOT proof that the failed operation succeeded. No inference accounting here.
Caps: 128 records, 16384 bytes/record, 1 MiB/event log, 4096 events/log and
4096 bytes/event line. Caps hard-fail; no eviction. Resource paths are host-only.
Private local owned files and cooperating locks are the trust boundary; malicious
same-UID wholesale rollback, filesystem snapshots and hostile servers are not
cryptographically detectable. Reads require existing locks and never create them.
Native placement receipts prove placement, never sight, continued ownership or
executable health. Unsupported or incomplete native chains require reconciliation.
"""

import os
from pathlib import Path
import re

from . import curio_store as store
from .director import State
from .protocol import parse_event, strict_json

MAX_RECORDS = 128
MAX_RECORD_BYTES = 16384
MAX_EVENT_BYTES = 1024 * 1024
MAX_EVENTS = 4096


def _path(path):
    value = str(Path(path).absolute())
    if len(value.encode()) > 2048 or ".." in Path(value).parts:
        raise ValueError("invalid host path")
    return value


def _inode(st):
    return [st.st_dev, st.st_ino]


def _file(directory, name, cap):
    before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    raw = store._read(directory, name, cap)
    store._same_entry(directory, name, before)
    return raw, dict(
        identity=_inode(before), length=len(raw), sha256=store._digest(raw)
    )


def _lifecycle(raw, used):
    if raw and not raw.endswith(b"\n"):
        raise ValueError("incomplete event line")
    lines = raw.splitlines()
    if len(lines) > MAX_EVENTS:
        raise ValueError("event count cap exceeded")
    state = State()
    status = "installed"
    pending = None
    admissions = 0
    applications = 0
    for index, line in enumerate(lines):
        if len(line) > 4096:
            raise ValueError("event line cap exceeded")
        try:
            e = parse_event(line)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid native event schema") from exc
        if e["seq"] != index + 1:
            raise ValueError("event sequence gap or rollback")
        if index == 0 and (e["event"], e["phase"], e["detail"]) != (
            "session",
            "result",
            "new",
        ):
            raise ValueError("full new-session history required")
        if e["event"] == "session":
            if e["phase"] != "result" or e["detail"] != (
                "new" if index == 0 else "restore"
            ):
                raise ValueError("conflicting session identity chain")
            if index == 0 and any(
                e[k] for k in ("safe", "spent", "reserved", "last_id")
            ):
                raise ValueError("invalid fresh session counters")
        state.ingest(e)  # includes safe/turn/spent/last_id rollback and death
        if pending is not None and e["event"] != "curio":
            raise ValueError("interrupted admission receipt chain")
        if e["event"] != "curio":
            continue
        detail = e["detail"]
        if e["phase"] != "result":
            raise ValueError("invalid curio receipt phase")
        if detail == "pre_admitted" and status == "installed" and pending is None:
            if not used:
                raise ValueError("admission missing exact used source")
            pending = e
        elif detail in ("admitted", "rejected") and pending is not None:
            if any(e[k] != pending[k] for k in ("safe", "turn", "last_id")) or e[
                "spent"
            ] != pending["spent"] + (detail == "admitted"):
                raise ValueError("conflicting admission cost/counters")
            status = detail
            admissions += detail == "admitted"
            pending = None
        elif detail == "rejected" and status == "installed":
            status = "rejected"
        elif (
            detail == "expired"
            and status in ("installed", "admitted")
            and pending is None
        ):
            status = "expired"
        elif detail == "placement_unavailable" and status == "admitted":
            pass
        elif detail in ("placed", "placement_failed") and status == "admitted":
            status = "placed" if detail == "placed" else "expired"
        elif status == "placed" and re.fullmatch(
            r"applied requested=(-[12]|[0-2]) actual=(-[12]|[0-2])", detail
        ):
            requested, actual = map(int, re.findall(r"=(-?\d+)", detail))
            if (
                applications >= 3
                or (requested >= 0 and not 0 <= actual <= requested)
                or (requested < 0 and not requested <= actual <= 0)
            ):
                raise ValueError("invalid application receipt")
            applications += 1
        else:
            raise ValueError("unsupported or conflicting curio lifecycle chain")
    if pending is not None or (used and not admissions and status != "rejected"):
        raise ValueError("ambiguous used source without final admission/rejection")
    return status


def _evidence(bundle_root, identity, run):
    c = store.read_candidate(bundle_root, identity)
    proof = dict(raw_sha256=store._digest(c.raw_response.encode()), run=None)
    raw = b""
    status = "authored"
    if run is not None:
        with store._directory(run) as d:
            with store._writer_lock(d, create=False):
                receipt = dict(
                    version=1,
                    status="candidate_installed_not_admitted",
                    source_sha256=identity,
                    provenance="supplied_raw_envelope",
                )
                store._verify(d, c.lua_source, receipt)
                files = {}
                for name in ("curio.lua", "curio-install.json", "curio-used.lua"):
                    if store._exists(d, name):
                        contents, files[name] = _file(d, name, 4096)
                        # Bind the bytes actually checkpointed, not a prior read
                        # by _verify: the sidecar lock does not freeze the engine.
                        if name == "curio-install.json":
                            store._json(contents, receipt)
                        elif contents != c.lua_source:
                            raise ValueError(
                                "checkpoint source conflicts with raw bundle"
                            )
                event = None
                if store._exists(d, "events.jsonl"):
                    raw, event = _file(d, "events.jsonl", MAX_EVENT_BYTES)
                status = _lifecycle(raw, "curio-used.lua" in files)
                proof["run"] = dict(
                    identity=_inode(os.fstat(d)), files=files, event=event
                )
                _validate_proof(proof)
                # Confirm the captured files still agree as a set. This detects
                # ordinary cross-file races, not an actively frozen game or
                # malicious same-UID ABA rewrites. Offline stability is required.
                for name, cap, expected in (
                    ("curio.lua", 4096, files.get("curio.lua")),
                    ("curio-install.json", 4096, files.get("curio-install.json")),
                    ("curio-used.lua", 4096, files.get("curio-used.lua")),
                    ("events.jsonl", MAX_EVENT_BYTES, event),
                ):
                    present = store._exists(d, name)
                    if present != (expected is not None) or (
                        present and _file(d, name, cap)[1] != expected
                    ):
                        raise ValueError("run evidence changed during snapshot")
                with store._directory(run) as current:
                    if _inode(os.fstat(current)) != proof["run"]["identity"]:
                        raise ValueError("run replaced during snapshot")
    return c, proof, raw, status


def _validate_proof(proof):
    if type(proof) is not dict or proof.keys() != {"raw_sha256", "run"}:
        raise ValueError("invalid proof schema")
    store._identity(proof["raw_sha256"])
    run = proof["run"]
    if run is None:
        return
    if type(run) is not dict or run.keys() != {"identity", "files", "event"}:
        raise ValueError("invalid run proof schema")

    def inode(value):
        if (
            type(value) is not list
            or len(value) != 2
            or any(type(n) is not int or n < 0 for n in value)
        ):
            raise ValueError("invalid inode identity")

    inode(run["identity"])
    files = run["files"]
    if (
        type(files) is not dict
        or not {"curio.lua", "curio-install.json"} <= files.keys()
        or not files.keys() <= {"curio.lua", "curio-install.json", "curio-used.lua"}
    ):
        raise ValueError("incomplete source/install checkpoint")
    for item in [
        *files.values(),
        *([run["event"]] if run["event"] is not None else []),
    ]:
        if type(item) is not dict or item.keys() != {"identity", "length", "sha256"}:
            raise ValueError("invalid file checkpoint schema")
        inode(item["identity"])
        if (
            type(item["length"]) is not int
            or not 0 <= item["length"] <= MAX_EVENT_BYTES
        ):
            raise ValueError("invalid checkpoint length")
        store._identity(item["sha256"])


def _match(old, new, raw):
    _validate_proof(old)
    _validate_proof(new)
    if old["raw_sha256"] != new["raw_sha256"]:
        raise ValueError("same source identity has conflicting raw/note evidence")
    a, b = old["run"], new["run"]
    if a is None:
        return
    if b is None or a["identity"] != b["identity"]:
        raise ValueError("run replaced or binding lost")
    for name, evidence in a["files"].items():
        if b["files"].get(name) != evidence:
            raise ValueError("source/install/used evidence replaced or changed")
    p, q = a["event"], b["event"]
    if p is not None and (
        q is None
        or p["identity"] != q["identity"]
        or p["length"] > len(raw)
        or store._digest(raw[: p["length"]]) != p["sha256"]
    ):
        raise ValueError("event checkpoint missing, replaced, truncated or rewritten")


def _names(d):
    names = set()
    with os.scandir(d) as entries:
        for entry in entries:
            if len(names) >= 2 * MAX_RECORDS + 2:
                raise ValueError("journal entry cap exceeded")
            names.add(entry.name)
    return names


def _load(d, growing=None):
    names = _names(d)
    store._json(store._read(d, "journal.json", 1024), {"version": 1})
    pairs = len(names - {"journal.json", ".director.lock"})
    if pairs % 2 or pairs // 2 > MAX_RECORDS:
        raise ValueError("incomplete journal/checkpoint or count cap")
    count = pairs // 2
    expected = {"journal.json", ".director.lock"} | {
        f"{i:06d}.{ext}" for i in range(1, count + 1) for ext in ("json", "commit")
    }
    if names != expected:
        raise ValueError("journal gap, duplicate or unknown evidence")
    latest = {}
    history = []
    previous = "0" * 64
    for i in range(1, count + 1):
        raw = store._read(d, f"{i:06d}.json", MAX_RECORD_BYTES)
        digest = store._digest(raw)
        if store._read(d, f"{i:06d}.commit", 64) != digest.encode():
            raise ValueError("missing/conflicting record checkpoint")
        r = strict_json(raw.decode("utf-8"), MAX_RECORD_BYTES)
        if (
            r.keys()
            != {
                "version",
                "seq",
                "previous",
                "op",
                "candidate_id",
                "bundle_root",
                "run",
                "proof",
            }
            or type(r["seq"]) is not int
            or r["seq"] != i
            or type(r["version"]) is not int
            or r["version"] != 1
            or r["previous"] != previous
        ):
            raise ValueError("journal schema/order conflict")
        identity = store._identity(r["candidate_id"])
        if (
            type(r["bundle_root"]) is not str
            or _path(r["bundle_root"]) != r["bundle_root"]
            or (
                r["run"] is not None
                and (type(r["run"]) is not str or _path(r["run"]) != r["run"])
            )
        ):
            raise ValueError("invalid persisted host path")
        old = latest.get(identity)
        if r["op"] == "register":
            if old is not None or r["run"] is not None:
                raise ValueError("duplicate/conflicting registration")
        elif r["op"] in ("bind", "observe"):
            if (
                old is None
                or old["bundle_root"] != r["bundle_root"]
                or r["run"] is None
            ):
                raise ValueError("missing registration/binding")
            if (r["op"] == "bind" and old["run"] is not None) or (
                r["op"] == "observe" and old["run"] != r["run"]
            ):
                raise ValueError("run binding conflict")
            if r["op"] == "bind" and any(x["run"] == r["run"] for x in latest.values()):
                raise ValueError("run already bound to another candidate")
        else:
            raise ValueError("unknown journal operation")
        latest[identity] = r
        history.append(r)
        previous = digest
    current = {}
    for identity, r in latest.items():
        current[identity] = _evidence(r["bundle_root"], identity, r["run"])
    previous_proof = {}
    for r in history:
        _, proof, raw, _ = current[r["candidate_id"]]
        old_proof = previous_proof.get(r["candidate_id"])
        _validate_proof(r["proof"])
        if (r["run"] is None) != (r["proof"]["run"] is None):
            raise ValueError("run binding and checkpoint schema disagree")
        if old_proof is not None:
            if r["op"] == "observe" and r["proof"] == old_proof:
                raise ValueError("duplicate observation checkpoint")
            _match(old_proof, r["proof"], raw)
            a, b = old_proof["run"], r["proof"]["run"]
            if (
                a
                and a["event"]
                and (
                    not b
                    or not b["event"]
                    or b["event"]["length"] < a["event"]["length"]
                )
            ):
                raise ValueError("journal event checkpoint rollback")
        previous_proof[r["candidate_id"]] = r["proof"]
        historical_run = r["proof"]["run"]
        if historical_run is not None:
            checkpoint = historical_run["event"]
            prefix = raw[: checkpoint["length"]] if checkpoint is not None else b""
            _lifecycle(prefix, "curio-used.lua" in historical_run["files"])
        try:
            _match(r["proof"], proof, raw)
        except (KeyError, TypeError) as exc:
            raise ValueError("invalid evidence checkpoint schema") from exc
        # Exact schema/type validation by reconstructing the historical snapshot.
        old = r["proof"]
        historical = dict(proof)
        if r["run"] is None:
            historical["run"] = None
        else:
            run = proof["run"]
            historical["run"] = dict(
                run,
                files={k: run["files"][k] for k in old["run"]["files"]},
                event=old["run"]["event"],
            )
        if store._encode(old) != store._encode(historical):
            raise ValueError("conflicting checkpoint schema")
    for identity, r in latest.items():
        if identity != growing and r["proof"] != current[identity][1]:
            raise ValueError("uncheckpointed evidence; explicit observe required")
    return latest, current, count, previous


def _append(d, count, previous, op, identity, bundle_root, run, proof):
    if count >= MAX_RECORDS:
        raise ValueError("journal record cap exceeded")
    raw = store._encode(
        dict(
            version=1,
            seq=count + 1,
            previous=previous,
            op=op,
            candidate_id=identity,
            bundle_root=bundle_root,
            run=run,
            proof=proof,
        )
    )
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError("journal record byte cap exceeded")
    name = f"{count + 1:06d}"
    store._publish(d, name + ".json", raw)
    store._publish(d, name + ".commit", store._digest(raw).encode())


def create_journal(root):
    """Explicit initial creation only; never use as restore/recovery."""
    with store._directory(root) as d:
        if _names(d):
            raise ValueError("journal creation requires an empty private root")
        with store._writer_lock(d, create=True):
            store._publish(d, "journal.json", store._encode({"version": 1}))
            _load(d)


def register(root, bundle_root, candidate_id):
    """Record proposal evidence, without claiming live/model authorship."""
    identity = store._identity(candidate_id)
    bundle_root = _path(bundle_root)
    with store._directory(root) as d, store._writer_lock(d, create=False):
        latest, _, count, previous = _load(d)
        if identity in latest:
            raise ValueError("candidate already registered")
        _, proof, _, _ = _evidence(bundle_root, identity, None)
        _append(d, count, previous, "register", identity, bundle_root, None, proof)
        _load(d)


def bind_run(root, candidate_id, run_directory):
    """Bind one host-selected installed run, not arbitrary caller status."""
    identity = store._identity(candidate_id)
    run = _path(run_directory)
    with store._directory(root) as d, store._writer_lock(d, create=False):
        latest, _, count, previous = _load(d)
        if (
            identity not in latest
            or latest[identity]["run"] is not None
            or any(r["run"] == run for r in latest.values())
        ):
            raise ValueError("missing registration or conflicting run binding")
        bundle = latest[identity]["bundle_root"]
        _, proof, _, _ = _evidence(bundle, identity, run)
        _append(d, count, previous, "bind", identity, bundle, run, proof)
        _load(d)


def observe(root, candidate_id):
    """Explicit durable checkpoint; ambiguous/malformed native histories reject."""
    identity = store._identity(candidate_id)
    with store._directory(root) as d, store._writer_lock(d, create=False):
        latest, current, count, previous = _load(d, growing=identity)
        if identity not in latest or latest[identity]["run"] is None:
            raise ValueError("candidate has no bound installation")
        r = latest[identity]
        proof = current[identity][1]
        if proof == r["proof"]:
            raise ValueError("no new evidence; refusing duplicate checkpoint")
        _append(
            d, count, previous, "observe", identity, r["bundle_root"], r["run"], proof
        )
        _load(d)


def prior_notes(root, *, limit=6):
    """Validate ALL history, then select <=6 notes in registration order.

    Caller may reduce limit for compose_prompt's aggregate cap; never truncate.
    This read certifies bytes only, never recovery of a failed previous fsync.
    """
    if type(limit) is not int or not 0 <= limit <= 6:
        raise ValueError("limit must be an integer in 0..6")
    with store._directory(root) as d, store._writer_lock(d, create=False):
        latest, current, _, _ = _load(d)
        selected = list(latest)[-limit:] if limit else []
        return [
            dict(
                candidate_id=i,
                status=current[i][3],
                continuity_note=current[i][0].continuity_note,
            )
            for i in selected
        ]
