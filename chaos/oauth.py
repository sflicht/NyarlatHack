"""Pinned ChatGPT OAuth calls, no agent/tool loop and no paid-API fallback.
NetHack General Public License. Run with the installed Hermes Python environment.
"""

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from urllib.parse import urlsplit
from . import curio_store as store
from .director import preferred_menu
from .protocol import parse_request, strict_json
from .response import normalize_whisper_response

MODEL = "gpt-5.6-luna"
PROVIDER = "openai-codex"
LIMIT = 20


def native_client():
    # Hermes owns the existing credential pool and refresh lock. Never copy tokens.
    from agent.auxiliary_client import _build_codex_client

    return _build_codex_client(MODEL)


CURIO_PURPOSE = "curio-generation"
CURIO_LIMIT = 2
_LEDGER_CAP = 32768
_BILLING = "subscription OAuth; cash charge not reported"
_USAGE = (
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
)


def _empty_ledger():
    return dict(
        model=MODEL,
        provider=PROVIDER,
        limit=LIMIT,
        cash_ceiling_usd=1,
        billing=_BILLING,
        paid_api_fallback=False,
        attempts=0,
        records=[],
    )


def _validate_ledger(data):
    expected = _empty_ledger()
    if type(data) is not dict or data.keys() != expected.keys():
        raise ValueError("invalid authorization ledger schema")
    for key in expected.keys() - {"attempts", "records"}:
        if type(data[key]) is not type(expected[key]) or data[key] != expected[key]:
            raise ValueError("invalid authorization ledger pin/limits")
    if (
        type(data["attempts"]) is not int
        or not 0 <= data["attempts"] <= LIMIT
        or type(data["records"]) is not list
        or len(data["records"]) != data["attempts"]
    ):
        raise ValueError("invalid authorization ledger count")
    scoped = 0
    for record in data["records"]:
        if (
            type(record) is not dict
            or not {"status", "prompt_sha256", "usage"} <= record.keys()
            or not record.keys()
            <= {"status", "prompt_sha256", "usage", "error_type", "purpose"}
            or type(record["status"]) is not str
            or record["status"] not in ("reserved", "completed", "failed")
        ):
            raise ValueError("invalid authorization record")
        store._identity(record["prompt_sha256"])
        if "purpose" in record:
            if type(record["purpose"]) is not str or record["purpose"] != CURIO_PURPOSE:
                raise ValueError("unknown authorization purpose")
            scoped += 1
        if "error_type" in record and (
            record["status"] != "failed"
            or type(record["error_type"]) is not str
            or not 1 <= len(record["error_type"]) <= 80
            or not record["error_type"].isidentifier()
        ):
            raise ValueError("invalid failure metadata")
        usage = record["usage"]
        if usage is not None and (
            type(usage) is not dict
            or not usage.keys() <= set(_USAGE)
            or any(
                type(n) is not int or not 0 <= n <= 2147483647 for n in usage.values()
            )
        ):
            raise ValueError("invalid usage metadata")
        if record["status"] == "reserved" and usage is not None:
            raise ValueError("reserved record cannot claim usage")
    if scoped > CURIO_LIMIT:
        raise ValueError("invalid curio authorization count")


class OAuthBackend:
    """One request, no retries. Curio reservations precede credential factories.

    purpose is None (legacy whisper) or literal curio-generation: two attempts
    within the SAME 20-record ledger. All reserved/completed/failed records count.
    A scoped call requires an existing ledger unless fresh_ledger=True explicitly
    allows initial creation, NEVER reset/recovery. Tests use temporary roots only.
    Legacy callers retain initial creation and route checks before reservation.
    require_existing=True disables parent/lock/ledger creation, including races;
    it retains the same global authorization limit and adds no new allowance.
    All calls preflight authorization before factory. No lock spans network I/O.

    last_receipt is known durable ledger data, NOT native acceptance. Lifecycle:
    reserved -> completed, or failed on request/transport validation failure;
    known usage is retained. Curio factory/route failures also spend a reservation.
    reservation_attempted signals possible consumption if durability failed.
    No retry/refund, even when complete bytes remain after a failed fsync.
    Scoped uncertainty retains evidence and forbids recovery status writes.
    Legacy failures clean only their own unpublished temporary and may durably
    mark a completion-sync failure as failed, without another provider request.
    """

    def __init__(
        self,
        ledger,
        *,
        timeout=60,
        ordinary_food=False,
        client_factory=native_client,
        purpose=None,
        fresh_ledger=False,
        require_existing=False,
    ):
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError("OAuth request timeout outside bounds")
        if purpose is not None and (
            type(purpose) is not str or purpose != CURIO_PURPOSE
        ):
            raise ValueError("unknown authorization purpose")
        if type(fresh_ledger) is not bool:
            raise ValueError("fresh_ledger must be boolean")
        if type(require_existing) is not bool or (require_existing and fresh_ledger):
            raise ValueError("invalid existing-ledger requirement")
        self.require_existing = require_existing
        self.ledger = Path(ledger).absolute()
        self.timeout = timeout
        self.deadline = float("inf")
        self.ordinary_food = ordinary_food
        self.factory = client_factory
        self.purpose = purpose
        self.fresh_ledger = not require_existing and (fresh_ledger or purpose is None)
        self.last_receipt = None
        self.reservation_attempted = False

    def _ledger_update(self, update, *, write=True, create_lock=True):
        if self.purpose is None and write and not self.require_existing:
            self.ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.require_existing:
            create_lock = False
        with store._directory(self.ledger.parent) as directory:
            lock_name = self.ledger.name + ".lock"
            flags = (os.O_RDWR if write else os.O_RDONLY) | (
                os.O_CREAT if create_lock else 0
            )
            lock = store._open_file(directory, lock_name, flags)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                store._same_entry(directory, lock_name, os.fstat(lock))
                with os.scandir(directory) as entries:
                    for i, entry in enumerate(entries):
                        if i >= 4096 or entry.name.startswith(".oauth-ledger-"):
                            raise ValueError(
                                "partial authorization evidence or directory cap"
                            )
                try:
                    raw = store._read(directory, self.ledger.name, _LEDGER_CAP)
                except FileNotFoundError:
                    if not self.fresh_ledger:
                        raise
                    data = _empty_ledger()
                else:
                    data = strict_json(raw.decode("utf-8"), _LEDGER_CAP)
                _validate_ledger(data)
                result = update(data)
                _validate_ledger(data)
                if not write:
                    return result
                raw = store._encode(data) + b"\n"
                if len(raw) > _LEDGER_CAP:
                    raise ValueError("ledger exceeds bound")
                name = ".oauth-ledger-" + uuid.uuid4().hex
                fd = store._open_file(
                    directory, name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                )
                published = False
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(raw)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(
                        name,
                        self.ledger.name,
                        src_dir_fd=directory,
                        dst_dir_fd=directory,
                    )
                    published = True
                    os.fsync(directory)
                    if store._read(directory, self.ledger.name, _LEDGER_CAP) != raw:
                        raise ValueError("authorization readback mismatch")
                    return result
                finally:
                    # Baseline whisper cleanup: only this unpublished name, never
                    # the published ledger. Scoped calls retain uncertain evidence.
                    if self.purpose is None and not published:
                        try:
                            os.unlink(name, dir_fd=directory)
                        except FileNotFoundError:
                            pass
            finally:
                os.close(lock)

    def _available(self, data):
        if data["attempts"] >= LIMIT:
            raise ValueError("milestone model request cap exhausted")
        if (
            self.purpose == CURIO_PURPOSE
            and sum(r.get("purpose") == CURIO_PURPOSE for r in data["records"])
            >= CURIO_LIMIT
        ):
            raise ValueError("curio model request cap exhausted")

    def preflight(self):
        """Read-only availability check; missing retained locks fail closed.

        Only legacy initial parent creation is retained. Scoped callers require
        existing private parents. Reservation repeats availability under lock.
        """
        if self.purpose is None and not self.require_existing:
            self.ledger.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with store._directory(self.ledger.parent) as directory:
            if not store._exists(directory, self.ledger.name):
                if not self.fresh_ledger:
                    raise FileNotFoundError("retained authorization ledger required")
                with os.scandir(directory) as entries:
                    for i, entry in enumerate(entries):
                        if i >= 4096 or entry.name.startswith(".oauth-ledger-"):
                            raise ValueError(
                                "partial authorization evidence or directory cap"
                            )
                if not store._exists(directory, self.ledger.name + ".lock"):
                    self._available(_empty_ledger())
                    return
        self._ledger_update(self._available, write=False, create_lock=False)

    def receipt(self, index):
        """Read an existing record; no creation, network or durability recovery."""
        if type(index) is not int or not 0 <= index < LIMIT:
            raise ValueError("invalid record index")

        def get(data):
            if index >= data["attempts"]:
                raise ValueError("missing authorization record")
            return dict(
                model=MODEL,
                provider=PROVIDER,
                record_index=index,
                record=copy.deepcopy(data["records"][index]),
            )

        return self._ledger_update(get, write=False, create_lock=False)

    def generate(self, instructions, prompt, *, return_receipt=False):
        if type(instructions) is not str or type(prompt) is not str:
            raise ValueError("text prompts required")
        if (
            len(instructions) + len(prompt) > 8192
            or len((instructions + prompt).encode()) > 8192
        ):
            raise ValueError("OAuth prompt exceeds byte cap")
        if type(return_receipt) is not bool:
            raise ValueError("return_receipt must be boolean")
        deadline = min(self.deadline, time.monotonic() + self.timeout)
        if deadline <= time.monotonic():
            raise TimeoutError("director deadline exhausted")
        self.last_receipt = None
        self.reservation_attempted = False
        self.preflight()
        digest = hashlib.sha256((instructions + "\0" + prompt).encode()).hexdigest()

        def reserve(data):
            self._available(data)  # Atomic check+append under the SAME ledger lock.
            index = data["attempts"]
            record = dict(status="reserved", prompt_sha256=digest, usage=None)
            if self.purpose is not None:
                record["purpose"] = self.purpose
            data["attempts"] += 1
            data["records"].append(record)
            return dict(
                model=MODEL,
                provider=PROVIDER,
                record_index=index,
                record=copy.deepcopy(record),
            )

        def reservation():
            self.reservation_attempted = True
            self.last_receipt = self._ledger_update(reserve)

        ledger_update_uncertain = False
        pending_record = None

        def record_status(status, **metadata):
            nonlocal ledger_update_uncertain
            index = self.last_receipt["record_index"]

            def change(data):
                nonlocal pending_record
                # Only legacy failure handling may accept our exact uncertain
                # completion bytes. Curio CAS never relaxes after a failed sync.
                legacy_failure = (
                    self.purpose is None
                    and ledger_update_uncertain
                    and status == "failed"
                    and data["records"][index] == pending_record
                )
                if (
                    data["records"][index] != self.last_receipt["record"]
                    and not legacy_failure
                ):
                    raise ValueError("authorization record changed")
                data["records"][index].update(status=status, **metadata)
                pending_record = copy.deepcopy(data["records"][index])
                return dict(
                    model=MODEL,
                    provider=PROVIDER,
                    record_index=index,
                    record=copy.deepcopy(data["records"][index]),
                )

            ledger_update_uncertain = True
            self.last_receipt = self._ledger_update(change)
            ledger_update_uncertain = False

        if self.purpose is not None:
            reservation()  # Durable BEFORE factory (which can refresh credentials).
        client = None
        try:
            client, model = self.factory()
            if client is None:
                raise ValueError("ChatGPT OAuth is unavailable")
            target = urlsplit(str(client.base_url))
            if (
                model != MODEL
                or target.scheme != "https"
                or target.hostname != "chatgpt.com"
                or target.path.rstrip("/") != "/backend-api/codex"
                or target.username
                or target.password
                or target.port not in (None, 443)
                or target.query
                or target.fragment
            ):
                raise ValueError(
                    "provider or model route is not the authorized subscription route"
                )
            client._real_client.max_retries = 0
            if self.purpose is None:
                reservation()
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise TimeoutError("director deadline exhausted")
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                tools=[],
                timeout=timeout,
                extra_body={"reasoning": {"effort": "low"}},
            )
            usage = {}
            for field in _USAGE:
                value = getattr(getattr(response, "usage", None), field, None)
                if type(value) is int and 0 <= value <= 2147483647:
                    usage[field] = value
            record_status("completed", usage=usage or None)
            choices = getattr(response, "choices", None)
            if (
                getattr(response, "model", None) != MODEL
                or type(choices) not in (list, tuple)
                or len(choices) != 1
            ):
                raise ValueError("unexpected response model/choices")
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if (
                getattr(message, "tool_calls", None)
                or getattr(message, "function_call", None)
                or type(content) is not str
                or len(content) > 8192
                or len(content.encode()) > 8192
            ):
                raise ValueError("unexpected tools or oversized/nontext output")
            return (
                (content, copy.deepcopy(self.last_receipt))
                if return_receipt
                else content
            )
        except Exception as exc:
            if self.last_receipt is not None and (
                self.purpose is None or not ledger_update_uncertain
            ):
                record_status("failed", error_type=type(exc).__name__)
            raise
        finally:
            if client is not None:
                client.close()

    def choose(self, state, ident, at):
        options = preferred_menu(state, self.ordinary_food)
        if not options:
            return None
        prompt = (Path(__file__).parent / "prompts/director.txt").read_text()
        content = self.generate(
            prompt,
            json.dumps(
                {
                    "assigned_id": ident,
                    "assigned_at": at,
                    "eligible": list(options),
                    "allowed_values": options,
                    "summary": json.loads(state.summary()),
                },
                separators=(",", ":"),
            ),
        )
        request = parse_request(normalize_whisper_response(content, cap=8192))
        if (
            request["id"] != ident
            or request["at"] != at
            or request["mutation"] not in options
            or request["value"] not in options[request["mutation"]]
        ):
            raise ValueError("model changed assigned schedule or eligibility")
        return request
