"""Pinned ChatGPT OAuth calls, no agent/tool loop and no paid-API fallback.
NetHack General Public License. Run with the installed Hermes Python environment.
"""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
from .director import secure_open, eligible
from .protocol import parse_request

MODEL = "gpt-5.6-luna"
PROVIDER = "openai-codex"
LIMIT = 20


def native_client():
    # Hermes owns the existing credential pool and refresh lock. Never copy tokens.
    from agent.auxiliary_client import _build_codex_client

    return _build_codex_client(MODEL)


class OAuthBackend:
    def __init__(
        self, ledger, *, timeout=60, ordinary_food=False, client_factory=native_client
    ):
        if not 0 < timeout <= 60:
            raise ValueError("OAuth request timeout outside bounds")
        self.ledger = Path(ledger).absolute()
        self.timeout = timeout
        self.deadline = float("inf")
        self.ordinary_food = ordinary_food
        self.factory = client_factory

    def _ledger_update(self, update):
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        lock = secure_open(str(self.ledger) + ".lock", os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                fd = secure_open(self.ledger)
            except FileNotFoundError:
                data = {
                    "model": MODEL,
                    "provider": PROVIDER,
                    "limit": LIMIT,
                    "cash_ceiling_usd": 1,
                    "billing": "subscription OAuth; cash charge not reported",
                    "paid_api_fallback": False,
                    "attempts": 0,
                    "records": [],
                }
            else:
                with os.fdopen(fd) as f:
                    raw = f.read(32769)
                if len(raw) > 32768:
                    raise ValueError("ledger exceeds bound")
                data = json.loads(raw)
                if (
                    data.get("model") != MODEL
                    or data.get("provider") != PROVIDER
                    or data.get("limit") != LIMIT
                    or type(data.get("attempts")) is not int
                    or not 0 <= data["attempts"] <= LIMIT
                    or len(data.get("records", [])) != data["attempts"]
                    or data.get("cash_ceiling_usd") != 1
                    or data.get("paid_api_fallback") is not False
                ):
                    raise ValueError("invalid authorization ledger")
            result = update(data)
            fd, name = tempfile.mkstemp(prefix=".oauth-ledger-", dir=self.ledger.parent)
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(data, f, sort_keys=True)
                    f.write("\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(name, self.ledger)
                directory = os.open(self.ledger.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return result
        finally:
            os.close(lock)

    def generate(self, instructions, prompt):
        if not isinstance(instructions, str) or not isinstance(prompt, str):
            raise ValueError("text prompts required")
        if len((instructions + prompt).encode()) > 8192:
            raise ValueError("OAuth prompt exceeds byte cap")
        timeout = min(self.timeout, self.deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("director deadline exhausted")
        client, model = self.factory()
        if client is None:
            raise ValueError("ChatGPT OAuth is unavailable")
        try:
            target = urlsplit(str(client.base_url))
            if (
                model != MODEL
                or target.scheme != "https"
                or target.hostname != "chatgpt.com"
                or target.path.rstrip("/") != "/backend-api/codex"
                or target.username
                or target.password
            ):
                raise ValueError(
                    "provider or model route is not the authorized subscription route"
                )
            client._real_client.max_retries = 0

            def reserve(data):
                if data["attempts"] >= LIMIT:
                    raise ValueError("milestone model request cap exhausted")
                index = data["attempts"]
                data["attempts"] += 1
                data["records"].append(
                    {
                        "status": "reserved",
                        "prompt_sha256": hashlib.sha256(
                            (instructions + "\0" + prompt).encode()
                        ).hexdigest(),
                        "usage": None,
                    }
                )
                return index

            index = self._ledger_update(reserve)
            try:
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
                for field in (
                    "input_tokens",
                    "output_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                ):
                    value = getattr(response.usage, field, None)
                    if type(value) is int and value >= 0:
                        usage[field] = value

                def completed(data):
                    data["records"][index].update(
                        status="completed", usage=usage or None
                    )

                self._ledger_update(completed)
                if response.model != MODEL or len(response.choices) != 1:
                    raise ValueError("unexpected response model/choices")
                message = response.choices[0].message
                if (
                    message.tool_calls
                    or not isinstance(message.content, str)
                    or len(message.content.encode()) > 8192
                ):
                    raise ValueError("unexpected tools or oversized/nontext output")
                return message.content
            except Exception as exc:
                error_name = type(exc).__name__

                def failed(data):
                    data["records"][index].update(
                        status="failed", error_type=error_name
                    )

                self._ledger_update(failed)
                raise
        finally:
            client.close()

    def choose(self, state, ident, at):
        options = eligible(state, self.ordinary_food)
        if not options:
            return None
        prompt = (Path(__file__).parent / "prompts/director.txt").read_text()
        request = parse_request(
            self.generate(
                prompt,
                json.dumps(
                    {
                        "assigned_id": ident,
                        "assigned_at": at,
                        "eligible": options,
                        "summary": json.loads(state.summary()),
                    },
                    separators=(",", ":"),
                ),
            )
        )
        if (
            request["id"] != ident
            or request["at"] != at
            or request["mutation"] not in options
        ):
            raise ValueError("model changed assigned schedule or eligibility")
        return request
