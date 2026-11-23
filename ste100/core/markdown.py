"""Markdown pre-pass: hide what is not prose, and keep every offset.

The masked text has the same length as the input, so the start and end of a
finding point into the original text.
"""

from __future__ import annotations

import re

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")

# A code span becomes one placeholder word. An all-capital word is a label to
# the vocabulary rules, so the placeholder is not reported.
_SPAN_FILL = "X"


def _blank(line: str) -> str:
    """Spaces in place of every character, except the line end."""
    body = line.rstrip("\r\n")
    return " " * len(body) + line[len(body) :]


def _mask_code_spans(line: str) -> str:
    return _CODE_SPAN.sub(lambda m: _SPAN_FILL * len(m.group(0)), line)


def mask_markdown(text: str) -> str:
    """Return ``text`` with fenced code blocks blanked and code spans masked."""
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        if fence is not None:
            out.append(_blank(line))
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
            continue
        opened = _FENCE_OPEN.match(line)
        if opened:
            fence = opened.group(1)
            out.append(_blank(line))
            continue
        out.append(_mask_code_spans(line))
    masked = "".join(out)
    assert len(masked) == len(text)
    return masked
