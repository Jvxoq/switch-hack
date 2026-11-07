"""Text cap shared by the tool server and the fix-PR tool. Kept apart so neither imports the other."""

from __future__ import annotations

MAX_TOOL_TEXT_CHARS = 20_000
CUT_MARK = "...[truncated]"


def cap_text(text: str, limit: int = MAX_TOOL_TEXT_CHARS) -> str:
    """Return at most `limit` characters, the cut mark included."""
    if len(text) <= limit:
        return text
    return text[: limit - len(CUT_MARK)] + CUT_MARK
