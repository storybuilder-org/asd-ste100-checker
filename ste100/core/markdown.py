"""Markdown pre-pass: hide what is not prose, and keep every offset.

The masked text has the same length as the input, so the start and end of a
finding point into the original text. The pre-pass also gives the offsets
where a sentence must start: each heading, each table cell, and the first
line of each block.
"""

from __future__ import annotations

import re

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_HEADING = re.compile(r"^( {0,3}#{1,6})(?=\s|$)")
_TABLE_DELIMITER = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")

# A code span becomes one placeholder word. An all-capital word is a label to
# the vocabulary rules, so the placeholder is not reported.
_SPAN_FILL = "X"


def _blank(line: str) -> str:
    """Spaces in place of every character, except the line end."""
    body = line.rstrip("\r\n")
    return " " * len(body) + line[len(body) :]


def _mask_code_spans(line: str) -> str:
    return _CODE_SPAN.sub(lambda m: _SPAN_FILL * len(m.group(0)), line)


def _first_text(line: str, offset: int) -> list[int]:
    """Offset of the first non-space character of ``line``, if any."""
    stripped = line.lstrip()
    if not stripped.strip():
        return []
    return [offset + len(line) - len(stripped)]


def prepare_markdown(text: str) -> tuple[str, list[int]]:
    """Return the masked text and the offsets where a sentence starts.

    - A fenced code block is blanked.
    - A code span becomes a placeholder word of the same length.
    - A heading marker and a table pipe become spaces. A table delimiter row
      is blanked.
    - A sentence starts at each heading, at each table cell, and at the first
      line after a blank line, a heading or a table row.
    """
    out: list[str] = []
    starts: list[int] = []
    fence: str | None = None
    new_block = True
    offset = 0
    for line in text.splitlines(keepends=True):
        here = offset
        offset += len(line)
        if fence is not None:
            out.append(_blank(line))
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                fence = None
                new_block = True
            continue
        opened = _FENCE_OPEN.match(line)
        if opened:
            fence = opened.group(1)
            out.append(_blank(line))
            continue
        if not line.strip():
            out.append(line)
            new_block = True
            continue

        masked = _mask_code_spans(line)
        heading = _HEADING.match(masked)
        if heading:
            marker = heading.group(1)
            masked = " " * len(marker) + masked[len(marker) :]
            starts.extend(_first_text(masked, here))
            out.append(masked)
            new_block = True
            continue
        if masked.lstrip().startswith("|"):
            if _TABLE_DELIMITER.match(masked):
                out.append(_blank(masked))
            else:
                cells = _UNESCAPED_PIPE.split(masked)
                pos = here
                for cell in cells:
                    starts.extend(_first_text(cell, pos))
                    pos += len(cell) + 1
                out.append(_UNESCAPED_PIPE.sub(" ", masked))
            new_block = True
            continue

        if new_block:
            starts.extend(_first_text(masked, here))
            new_block = False
        out.append(masked)

    result = "".join(out)
    assert len(result) == len(text)
    return result, starts


def mask_markdown(text: str) -> str:
    """Return ``text`` with code hidden. See :func:`prepare_markdown`."""
    return prepare_markdown(text)[0]
