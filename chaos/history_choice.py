"""Bounded selectors for host-built history candidates (NGPL).

The checked history consumer owns evidence and eligibility. This boundary accepts
its public context, never source proofs or raw events. The live runner must still
recheck the source and schedule after selection, before publishing anything.
"""

import copy
import json
from pathlib import Path
import random
import time

from .protocol import encode_request, parse_request, strict_json
from .response import normalize_whisper_response

_CONTEXT_FIELDS = frozenset(
    ("history_context_v", "summary", "episodes", "prior_whispers", "prior_coverage")
)


class _BoundedChoice:
    def __init__(self, *, max_attempts=1):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 2:
            raise ValueError("pilot requires one or two bounded decision attempts")
        self.max_attempts = max_attempts
        self.attempts = 0
        self.deadline = float("inf")
        self.last_receipt = None
        self.last_response = None
        self.instructions = (
            Path(__file__).parent / "prompts/history-director.txt"
        ).read_text(encoding="utf-8")

    def _prepare(self, context, allowed_requests):
        self.last_receipt = self.last_response = None
        if type(allowed_requests) is not list or len(allowed_requests) > 2:
            raise ValueError("bounded candidate list required")
        # Freeze independent canonical copies; never let output mutate the menu.
        menu = [parse_request(encode_request(r)) for r in allowed_requests]
        if len({encode_request(r) for r in menu}) != len(menu):
            raise ValueError("duplicate candidate")
        if not menu or self.attempts >= self.max_attempts:
            return None
        if (
            type(context) is not dict
            or set(context) != _CONTEXT_FIELDS
            or type(context["history_context_v"]) is not int
            or context["history_context_v"] != 1
        ):
            raise ValueError("public history context required, without host proof")
        try:
            prompt = json.dumps(
                {"context": context, "allowed_requests": menu},
                allow_nan=False,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("bounded JSON public context required") from exc
        if len((self.instructions + prompt).encode("utf-8")) > 8192:
            raise ValueError("history prompt exceeds transport byte cap")
        if time.monotonic() >= self.deadline:
            raise TimeoutError("history decision deadline exhausted")
        return menu, prompt


class RandomHistoryBackend(_BoundedChoice):
    """Reproducible offline choice, not model-authored evidence."""

    def __init__(self, seed, *, max_attempts=1):
        super().__init__(max_attempts=max_attempts)
        if type(seed) is not int:
            raise ValueError("explicit integer director seed required")
        self.rng = random.Random(seed)

    def choose(self, context, allowed_requests):
        prepared = self._prepare(context, allowed_requests)
        if prepared is None:
            return None
        menu, _ = prepared
        self.attempts += 1
        return self.rng.choice(menu)


class OAuthHistoryBackend(_BoundedChoice):
    """Use an existing pinned OAuthBackend; never create a ledger or fallback.

    The caller must require the existing ledger before constructing that transport.
    Failures spend this selector's attempt even when transport preflight prevents
    a provider request. Actual provider reservations remain the transport's ledger.
    """

    def __init__(self, transport, *, max_attempts=1):
        super().__init__(max_attempts=max_attempts)
        self.transport = transport

    def choose(self, context, allowed_requests):
        prepared = self._prepare(context, allowed_requests)
        if prepared is None:
            return None
        menu, prompt = prepared
        self.transport.deadline = min(self.deadline, self.transport.deadline)
        self.attempts += 1  # No automatic retry after transport or schema failure.
        content, receipt = self.transport.generate(
            self.instructions, prompt, return_receipt=True
        )
        text = normalize_whisper_response(content, cap=8192)
        self.last_response = content
        self.last_receipt = copy.deepcopy(receipt)
        decoded = strict_json(text, 512)
        if set(decoded) == {"abstain"} and decoded["abstain"] is True:
            return None
        request = parse_request(text)
        if request not in menu:
            raise ValueError("history choice is outside the frozen candidate menu")
        return request
