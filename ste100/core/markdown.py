"""Markdown pre-pass: find the structure, and keep every offset.

The returned text has the same length as the input, so the start and end of
a finding point into the original text. The pre-pass gives:

- the offsets where a sentence must start: each heading, each table cell,
  and the first line of each block;
- the character ranges of code spans, each of which is one name.
"""

from __future__ import annotations

import re

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_HEADING = re.compile(r"^( {0,3}#{1,6})(?=\s|$)")
_TABLE_DELIMITER = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _blank(line: str) -> str:
    """Spaces in place of every character, except the line end."""
    body = line.rstrip("\r\n")
    return " " * len(body) + line[len(body) :]


def _first_text(line: str, offset: int) -> list[int]:
    """Offset of the first non-space character of ``line``, if any."""
    stripped = line.lstrip()
    if not stripped.strip():
        return []
    return [offset + len(line) - len(stripped)]


def _code_spans(line: str) -> list[tuple[int, int]]:
    """(start, end) of the content of each code span, inside ``line``."""
    out = []
    for m in _CODE_SPAN.finditer(line):
        start, end = m.start(2), m.end(2)
        content = m.group(2)
        start += len(content) - len(content.lstrip())
        end -= len(content) - len(content.rstrip())
        if start < end:
            out.append((start, end))
    return out


# Characters that mark the content of a code span as code, not a name or text.
_CODE_CHARS = frozenset("(){}[]<>=;\\\"',?!&*+|")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_LINK = re.compile(r"!?\[([^\]\n]*)\]\(([^)\s]+)\)")


def _blank_link_markup(line: str, spans: list[tuple[int, int]]) -> str:
    """Spaces in place of the markup of each inline link: ``[``, ``](`` and
    ``)``. The link text and the URL stay. A link inside a code span is not
    markup."""
    chars = list(line)
    for m in _LINK.finditer(line):
        if any(s <= m.start() < e for s, e in spans):
            continue
        markup = [*range(m.start(), m.start(1)), m.end(1), m.end(1) + 1, m.end() - 1]
        for i in markup:
            chars[i] = " "
    return "".join(chars)


def _table_pipes(line: str, spans: list[tuple[int, int]]) -> list[int]:
    """Positions of the cell separators: unescaped pipes outside code spans."""
    pipes = []
    for i, ch in enumerate(line):
        if ch != "|" or (i > 0 and line[i - 1] == "\\"):
            continue
        if any(s - 1 <= i <= e for s, e in spans):
            continue
        pipes.append(i)
    return pipes


def prepare_markdown(text: str) -> tuple[str, list[int], list[tuple[int, int]]]:
    """Return the prepared text, the sentence starts, and the code-span ranges.

    - A fenced code block is blanked: the standards do not apply to code.
    - A heading marker, a table pipe and a table delimiter row become spaces.
    - A sentence starts at each heading, at each table cell, and at the first
      line after a blank line, a heading or a table row.
    """
    out: list[str] = []
    starts: list[int] = []
    names: list[tuple[int, int]] = []
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

        spans = _code_spans(line)
        line = _blank_link_markup(line, spans)
        for s, e in spans:
            content = line[s:e]
            if any(ch in _CODE_CHARS for ch in content):
                # Code: each name in it is checked. The characters between the
                # names (numbers, punctuation) become spaces, so the tokenizer
                # does not join them to a name.
                found = [(s + m.start(), s + m.end()) for m in _IDENTIFIER.finditer(content)]
                chars = list(line)
                for i in range(s, e):
                    if not any(a <= i < b for a, b in found):
                        chars[i] = " "
                line = "".join(chars)
                names.extend((here + a, here + b) for a, b in found)
            elif " " not in content:
                names.append((here + s, here + e))  # one name: a file, a path
            # Otherwise the span quotes text, and its words are checked as words.

        heading = _HEADING.match(line)
        if heading:
            marker = heading.group(1)
            line = " " * len(marker) + line[len(marker) :]
            starts.extend(_first_text(line, here))
            out.append(line)
            new_block = True
            continue
        if line.lstrip().startswith("|"):
            if _TABLE_DELIMITER.match(line):
                out.append(_blank(line))
            else:
                pipes = _table_pipes(line, spans)
                chars = list(line)
                cell_start = 0
                for p in [*pipes, len(line)]:
                    starts.extend(_first_text(line[cell_start:p], here + cell_start))
                    cell_start = p + 1
                for p in pipes:
                    chars[p] = " "
                out.append("".join(chars))
            new_block = True
            continue

        if new_block:
            starts.extend(_first_text(line, here))
            new_block = False
        out.append(line)

    result = "".join(out)
    assert len(result) == len(text)
    return result, starts, names
