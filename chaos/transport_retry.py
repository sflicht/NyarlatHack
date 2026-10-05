"""Transport-only retry hints, never request/ledger policy (NGPL).

Backends call this only for a send failure, after distinguishing it from
credential, route, response-validation and ledger failures. Authoring owns the
retry count and the single overall deadline. No error bodies or headers are
written to evidence.
"""

from datetime import timezone
from email.utils import parsedate_to_datetime
import math
import time


def retry_delay(error, *, status=None, retry_after=None):
    """Seconds to wait, or None for a non-retryable transport failure.

    Retry-After accepts HTTP delta seconds and HTTP dates. Invalid hints fall
    back to one second; valid hints are never capped downward to fit a deadline.
    The caller must abandon a retry that cannot fit in the remaining time.
    """
    if status is None:
        status = getattr(error, "status_code", None)
    if (
        status is not None
        and status not in (408, 429)
        and not (type(status) is int and 500 <= status <= 599)
    ):
        return None
    if status is None and not isinstance(error, (OSError, RuntimeError)):
        return None
    if retry_after is None:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", {})
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if isinstance(retry_after, str):
        if retry_after.isascii() and retry_after.isdecimal():
            # Avoid huge integers supplied by a remote header. Infinity means
            # no retry can fit; it does NOT mean retry immediately.
            return float(retry_after) if len(retry_after) < 16 else math.inf
        try:
            date = parsedate_to_datetime(retry_after)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            return max(0.0, date.timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            pass
    return 1.0
