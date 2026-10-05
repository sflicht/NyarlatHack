"""xAI model-authoring transports and their ledger (NGPL; see dat/license).

Two providers (chaos/author_config.py):

- ``xai-oauth``: Hermes's xAI OAuth login. Hermes owns the credential pool
  and refresh; this module imports Hermes lazily, so the repository works
  without it, and never reads, copies or logs a token.
- ``xai``: the xAI API with a key read from the user's environment when the
  backend is built (``XAI_API_KEY``, or the variable named by
  ``--api-key-env``). The key is held only in memory for the request header.
  It is never logged, written to the ledger, receipts or run evidence, put in
  an exception message or a repr.

Every HTTP attempt is reserved durably in the ledger *before* any credential
is resolved or any request is sent, so a killed request is still counted.
Hermes is imported when the xai-oauth backend is built, before any
reservation, because that import may re-exec into Hermes's interpreter.
Caps: per surface per game, per day, per ledger file. No automatic retry:
one ``generate`` call is at most one request.
"""

import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid
from urllib.parse import urlsplit

from .author_config import AuthorConfig

XAI_HOST = "api.x.ai"
XAI_BASE_URL = "https://api.x.ai/v1"
ROUTES = {"xai-oauth": "hermes-xai-oauth", "xai": "xai-api-key"}

SURFACE_GAME_CAP = 3
DAILY_CAP = 200
FILE_CAP = 2000
MAX_PROMPT_BYTES = 32768
MAX_RESPONSE_BYTES = 16384
_MAX_TIMEOUT = 600
_LEDGER_BYTES = 8 * 1024 * 1024
_USAGE = (
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
)
_ROW_KEYS = {
    "v",
    "attempt",
    "status",
    "provider",
    "model",
    "route",
    "time",
    "day",
    "run_id",
    "surface",
    "prompt_sha256",
    "http_status",
    "latency_s",
    "usage",
    "response_sha256",
    "error_type",
}
_ID = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")


class NoModelReachable(RuntimeError):
    """A configured provider cannot be used right now (missing credential,
    Hermes absent). Callers treat it as "no model content this game"."""


class LedgerCapReached(RuntimeError):
    """A cap would be exceeded; nothing was reserved or sent."""


def default_ledger():
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "nyarlathack" / "xai-ledger.jsonl"


def _label(value, what):
    if type(value) is not str or not 1 <= len(value) <= 64 or not set(value) <= _ID:
        raise ValueError(f"invalid {what}")
    return value


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class XaiLedger:
    """Append-only JSON-lines ledger, one private file, flock-serialised.

    A request is two rows sharing an ``attempt`` id: ``reserved`` (written and
    fsynced before the request) then ``completed`` or ``failed``. Caps count
    reservations, so an unfinished attempt still counts.
    """

    def __init__(
        self,
        path=None,
        *,
        surface_game_cap=SURFACE_GAME_CAP,
        daily_cap=DAILY_CAP,
        file_cap=FILE_CAP,
    ):
        for cap in (surface_game_cap, daily_cap, file_cap):
            if type(cap) is not int or not 1 <= cap <= FILE_CAP:
                raise ValueError("ledger cap outside bounds")
        self.path = Path(default_ledger() if path is None else path).absolute()
        self.surface_game_cap = surface_game_cap
        self.daily_cap = daily_cap
        self.file_cap = file_cap

    def _open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(
            self.path,
            os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            st = os.fstat(fd)
            if st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ValueError("ledger must be a private file owned by this user")
            fcntl.flock(fd, fcntl.LOCK_EX)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @staticmethod
    def _rows(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        raw = b""
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            raw += chunk
            if len(raw) > _LEDGER_BYTES:
                raise ValueError("ledger exceeds bound")
        if raw and not raw.endswith(b"\n"):
            raise ValueError("ledger has a partial row")
        rows = []
        for line in raw.splitlines():
            row = json.loads(line)
            if type(row) is not dict or set(row) != _ROW_KEYS or row["v"] != 1:
                raise ValueError("invalid ledger row")
            rows.append(row)
        return rows

    @staticmethod
    def _append(fd, row):
        os.write(fd, json.dumps(row, sort_keys=True).encode() + b"\n")
        os.fsync(fd)

    def rows(self):
        fd = self._open()
        try:
            return self._rows(fd)
        finally:
            os.close(fd)

    def _check(self, rows, run_id, surface, day):
        reserved = [r for r in rows if r["status"] == "reserved"]
        if len(reserved) >= self.file_cap:
            raise LedgerCapReached("ledger file cap reached")
        if sum(r["day"] == day for r in reserved) >= self.daily_cap:
            raise LedgerCapReached("daily request cap reached")
        if (
            sum(r["run_id"] == run_id and r["surface"] == surface for r in reserved)
            >= self.surface_game_cap
        ):
            raise LedgerCapReached("per-surface per-game cap reached")

    def preflight(self, run_id, surface):
        now = time.time()
        fd = self._open()
        try:
            self._check(
                self._rows(fd),
                run_id,
                surface,
                time.strftime("%Y-%m-%d", time.gmtime(now)),
            )
        finally:
            os.close(fd)

    def reserve(self, config, run_id, surface, prompt_sha256):
        now = time.time()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        row = dict(
            v=1,
            attempt=uuid.uuid4().hex,
            status="reserved",
            provider=config.provider,
            model=config.model,
            route=ROUTES[config.provider],
            time=round(now, 3),
            day=day,
            run_id=run_id,
            surface=surface,
            prompt_sha256=prompt_sha256,
            http_status=None,
            latency_s=None,
            usage=None,
            response_sha256=None,
            error_type=None,
        )
        fd = self._open()
        try:
            self._check(self._rows(fd), run_id, surface, day)
            self._append(fd, row)
        finally:
            os.close(fd)
        return dict(row)

    def finish(self, reserved, status, **fields):
        if status not in ("completed", "failed"):
            raise ValueError("invalid ledger status")
        row = dict(reserved, status=status, time=round(time.time(), 3))
        row.update(fields)
        if set(row) != _ROW_KEYS:
            raise ValueError("invalid ledger fields")
        fd = self._open()
        try:
            if not any(
                r["attempt"] == reserved["attempt"] and r["status"] == "reserved"
                for r in self._rows(fd)
            ):
                raise ValueError("finishing an attempt that was never reserved")
            self._append(fd, row)
        finally:
            os.close(fd)
        return dict(row)


class _HttpClient:
    """Minimal xAI chat-completions client for the API-key provider.

    http.client only (no SDK, redirects or retries). The key lives in a
    private attribute; repr and every error omit it.
    """

    def __init__(self, key, base_url=XAI_BASE_URL):
        self.__key = key
        self.base_url = base_url
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.last_status = None
        self.last_retry_after = None

    def __repr__(self):
        return f"<xai http client {self.base_url}>"

    def close(self):
        pass

    def _create(self, *, model, messages, timeout, tools=None, **_ignored):
        self.last_status = None
        self.last_retry_after = None
        body = json.dumps(
            {"model": model, "messages": messages, "stream": False}
        ).encode()
        conn = http.client.HTTPSConnection(XAI_HOST, 443, timeout=timeout)
        try:
            conn.request(
                "POST",
                urlsplit(self.base_url).path.rstrip("/") + "/chat/completions",
                body=body,
                headers={
                    "Authorization": "Bearer " + self.__key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            response = conn.getresponse()
            self.last_status = response.status
            self.last_retry_after = (
                response.getheader("Retry-After")
                if hasattr(response, "getheader")
                else None
            )
            raw = response.read(MAX_RESPONSE_BYTES * 4 + 1)
        finally:
            conn.close()
        if self.last_status != 200:
            raise RuntimeError(f"xAI HTTP status {self.last_status}")
        if len(raw) > MAX_RESPONSE_BYTES * 4:
            raise ValueError("xAI response exceeds bound")
        data = json.loads(raw)
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content=(c.get("message") or {}).get("content"),
                    tool_calls=(c.get("message") or {}).get("tool_calls"),
                    function_call=None,
                )
            )
            for c in data.get("choices") or []
        ]
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        return SimpleNamespace(
            model=data.get("model"),
            choices=choices,
            usage=SimpleNamespace(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                reasoning_tokens=details.get("reasoning_tokens"),
            ),
        )


def _hermes_xai_builder():
    """Hermes's xAI OAuth client builder, imported lazily.

    Imported when the backend is built, never per request: importing Hermes
    may re-exec the interpreter into Hermes's runtime, which must happen
    before any attempt is reserved.
    """
    try:
        from agent.auxiliary_client import _build_xai_oauth_aux_client
    except ImportError:
        raise NoModelReachable(
            "xai-oauth needs Hermes (agent.auxiliary_client)"
        ) from None
    return _build_xai_oauth_aux_client


def _oauth_factory(builder, model):
    def factory():
        client, served = builder(model)
        if client is None:
            raise NoModelReachable("xai-oauth: no Hermes xAI OAuth login")
        return client, served

    return factory


class XaiBackend:
    """One configured xAI provider and model, ledgered per request.

    ``generate(instructions, prompt)`` returns the reply text (and, with
    ``return_receipt=True``, a receipt naming provider, model, route and the
    ledger row). ``client_factory`` is the offline test seam: a callable
    returning ``(client, model)`` with an OpenAI-shaped ``chat.completions``.
    """

    def __init__(
        self,
        config,
        ledger,
        *,
        run_id,
        surface,
        timeout=420,
        client_factory=None,
        environ=None,
    ):
        if type(config) is not AuthorConfig or config.provider not in ROUTES:
            raise ValueError("xAI backend needs an xai or xai-oauth configuration")
        if type(ledger) is not XaiLedger:
            raise ValueError("xAI backend needs an XaiLedger")
        if type(timeout) not in (int, float) or not 0 < timeout <= _MAX_TIMEOUT:
            raise ValueError("request timeout outside bounds")
        self.config = config
        self.ledger = ledger
        self.run_id = _label(run_id, "run id")
        self.surface = _label(surface, "surface")
        self.timeout = timeout
        self.deadline = float("inf")
        self.last_receipt = None
        self.reservation_attempted = False
        if client_factory is not None:
            self._factory = client_factory
        elif config.provider == "xai-oauth":
            self._factory = _oauth_factory(_hermes_xai_builder(), config.model)
        else:
            env = os.environ if environ is None else environ
            name = config.key_env or ""
            # Read once, at build time, from the environment only.
            key = env.get(name)
            if not key:
                raise NoModelReachable(f"{name} is not set")
            if any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise NoModelReachable(f"{name} is not a usable key")
            client = _HttpClient(key)
            del key
            self._factory = lambda: (client, config.model)

    def __repr__(self):
        return (
            f"<XaiBackend provider={self.config.provider} model={self.config.model} "
            f"surface={self.surface}>"
        )

    def preflight(self):
        self.ledger.preflight(self.run_id, self.surface)

    def _receipt(self, row):
        return dict(
            provider=self.config.provider,
            model=self.config.model,
            route=ROUTES[self.config.provider],
            record=dict(row),
        )

    def generate(self, instructions, prompt, *, return_receipt=False):
        if type(instructions) is not str or type(prompt) is not str:
            raise ValueError("text prompts required")
        if len((instructions + prompt).encode()) > MAX_PROMPT_BYTES:
            raise ValueError("prompt exceeds byte cap")
        deadline = min(self.deadline, time.monotonic() + self.timeout)
        if deadline <= time.monotonic():
            raise TimeoutError("authoring deadline exhausted")
        self.last_receipt = None
        self.retry_delay = None
        self.reservation_attempted = True
        reserved = self.ledger.reserve(
            self.config, self.run_id, self.surface, _sha(instructions + "\0" + prompt)
        )
        self.last_receipt = self._receipt(reserved)
        started = time.monotonic()
        client = None
        status = None
        retry_wait = None
        try:
            client, served = self._factory()
            if client is None:
                raise NoModelReachable("no xAI client")
            target = urlsplit(str(client.base_url))
            if (
                served != self.config.model
                or target.scheme != "https"
                or target.hostname != XAI_HOST
                or target.username
                or target.password
                or target.port not in (None, 443)
                or target.query
                or target.fragment
            ):
                raise ValueError("provider route or model is not the configured one")
            real = getattr(client, "_real_client", None)
            if real is not None and hasattr(real, "max_retries"):
                real.max_retries = 0
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("authoring deadline exhausted")
            try:
                response = client.chat.completions.create(
                    model=self.config.model,
                    messages=[
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": prompt},
                    ],
                    tools=[],
                    timeout=remaining,
                )
            except Exception as exc:
                from .transport_retry import retry_delay

                status = getattr(exc, "status_code", None) or getattr(
                    client, "last_status", None
                )
                retry_wait = retry_delay(
                    exc,
                    status=status,
                    retry_after=getattr(client, "last_retry_after", None),
                )
                raise
            status = getattr(client, "last_status", None) or 200
            usage = {}
            for field in _USAGE:
                value = getattr(getattr(response, "usage", None), field, None)
                if type(value) is int and 0 <= value <= 2147483647:
                    usage[field] = value
            choices = getattr(response, "choices", None)
            if (
                getattr(response, "model", None) != self.config.model
                or not isinstance(choices, (list, tuple))
                or len(choices) != 1
            ):
                raise ValueError("unexpected response model or choices")
            message = getattr(choices[0], "message", None)
            content = getattr(message, "content", None)
            if (
                getattr(message, "tool_calls", None)
                or getattr(message, "function_call", None)
                or type(content) is not str
                or len(content.encode()) > MAX_RESPONSE_BYTES
            ):
                raise ValueError("unexpected tools or oversized/nontext output")
            row = self.ledger.finish(
                reserved,
                "completed",
                http_status=status,
                latency_s=round(time.monotonic() - started, 3),
                usage=usage or None,
                response_sha256=_sha(content),
            )
            self.last_receipt = self._receipt(row)
            return (content, dict(self.last_receipt)) if return_receipt else content
        except Exception as exc:
            if status is None and client is not None:
                status = getattr(client, "last_status", None)
            row = self.ledger.finish(
                reserved,
                "failed",
                http_status=status,
                latency_s=round(time.monotonic() - started, 3),
                error_type=type(exc).__name__[:80],
            )
            self.last_receipt = self._receipt(row)
            # Only a known-durable failed reservation permits a retry. Ledger
            # uncertainty must never become an extra provider request.
            self.retry_delay = retry_wait
            raise
        finally:
            if client is not None:
                client.close()


class XaiOAuthBackend(XaiBackend):
    """``xai-oauth``: Hermes's xAI OAuth login; NyarlatHack holds no key."""

    def __init__(self, config, ledger, **kwargs):
        if type(config) is not AuthorConfig or config.provider != "xai-oauth":
            raise ValueError("XaiOAuthBackend needs provider xai-oauth")
        super().__init__(config, ledger, **kwargs)


class XaiApiKeyBackend(XaiBackend):
    """``xai``: key from XAI_API_KEY, or the variable named by --api-key-env."""

    def __init__(self, config, ledger, **kwargs):
        if type(config) is not AuthorConfig or config.provider != "xai":
            raise ValueError("XaiApiKeyBackend needs provider xai")
        super().__init__(config, ledger, **kwargs)


def build(config, ledger, *, run_id, surface, **kwargs):
    """The xAI backend for a configuration, or None when nothing is configured.

    Raises NoModelReachable when the provider is configured but unusable
    (no Hermes login, key variable unset): no model content this game.
    """
    if config is None:
        return None
    cls = {"xai-oauth": XaiOAuthBackend, "xai": XaiApiKeyBackend}.get(config.provider)
    if cls is None:
        raise ValueError("not an xAI provider")
    return cls(config, ledger, run_id=run_id, surface=surface, **kwargs)
