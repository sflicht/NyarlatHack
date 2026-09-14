"""Formatting-only cleanup at model whisper boundaries (NGPL)."""

import re


_FENCE = re.compile(r"```(?:json)?\r?\n(.*?)\r?\n```", re.DOTALL)
_WHITESPACE = " \t\r\n"  # Only the whitespace admitted by the JSON protocol.


def normalize_whisper_response(content, *, cap):
    """Remove surrounding whitespace and at most one bare/json enclosing fence.

    Bound the original UTF-8 response before stripping. Never extract an object
    from prose, recursively unwrap, or decode/re-encode JSON: the caller must
    still use parse_request and enforce its assigned schedule and eligibility.
    This is not for general text generation or exact-source Lua candidates.
    """
    if not isinstance(content, str) or len(content.encode("utf-8")) > cap:
        raise ValueError("whisper response is nontext or exceeds byte cap")
    text = content.strip(_WHITESPACE)
    if "```" in text:
        match = _FENCE.fullmatch(text)
        if match is None or "```" in match[1]:
            raise ValueError("whisper response requires one full bare/json fence")
        text = match[1].strip(_WHITESPACE)
    return text
