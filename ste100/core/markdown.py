"""Markdown pre-pass: find the structure, and keep every offset.

The returned text has the same length as the input, so the start and end of
a finding point into the original text. The pre-pass gives:

- the offsets where a sentence must start: each heading, each table cell,
  and the first line of each block;
- the character ranges of the names: a code span that is one name, and
  each name inside code.
"""

from __future__ import annotations

import re

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
_HEADING = re.compile(r"^( {0,3}#{1,6})(?=\s|$)")
# A list item: "- ", "* ", "+ " or "1. " at the start of a line.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
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


def _blank_backticks(line: str) -> str:
    """Spaces in place of the backticks that open and close each code span.
    They are markup; left in, the tokenizer joins two names around them."""
    chars = list(line)
    for m in _CODE_SPAN.finditer(line):
        ticks = len(m.group(1))
        for i in [*range(m.start(), m.start() + ticks), *range(m.end() - ticks, m.end())]:
            chars[i] = " "
    return "".join(chars)


# Characters that mark the content of a code span as code, not a name or text.
_CODE_CHARS = frozenset("(){}[]<>=;\\\"',?!&*+|")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# In code, a word of lower-case letters only is a code word: English text (a
# message, a comment) or a command or keyword. If the dictionary approves it in
# any part of speech, it gets no finding; if not, it is a name and a glossary
# must list it. Any other word in code is a name.
_LOWERCASE_WORD = re.compile(r"^[a-z]+$")
# A file path with no space: D:\dev\src\CLAUDE.md, ~/.claude/CLAUDE.md.
_PATH_CONTENT = re.compile(r"^(?:[A-Za-z]:)?[\w.~-]*(?:[\\/][\w.~-]+)+[\\/]?$")

_CODE_URL = re.compile(r"https?://[^\s\"'`<>()\[\]{}]*[^\s\"'`<>()\[\]{}.,;:!?]")
# A placeholder such as <n> is part of the word around it.
_CODE_CHUNK = re.compile(r"(?:<\w+>|[^\s\"'`<>()\[\]{}=;,|&*+!?])+")
# A path inside code: a drive and backslashes (D:\dev\src), or a word and
# forward slashes (process/word-lists/shared.yaml, ~/.claude). An RTF code
# such as \rtf1 or a\par is not a path.
_SEG = r"(?:<\w+>|[\w.~-])+"
_CODE_PATH = re.compile(rf"^(?:[A-Za-z]:(?:\\{_SEG})+\\?|{_SEG}(?:/{_SEG})+/?)$")
# A command option: -x or --name.
_CODE_OPTION = re.compile(r"^--?[A-Za-z][\w-]*$")
# A name joined with hyphens, such as a package name: asd-ste100-checker,
# en_core_web_sm-3.8.0.
_CODE_HYPHENATED = re.compile(r"^[A-Za-z][\w.]*(?:-[\w.]*\w)+$")
_HAS_OPTION = re.compile(r"(?:^|\s)--?[A-Za-z]")


def _words_in_code(code: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_name) of each word in a piece of code.

    A URL, a path or a command option is one name. Each other word is an
    identifier: a name, or English text if it is lower-case letters only.
    """
    taken: list[tuple[int, int]] = [m.span() for m in _CODE_URL.finditer(code)]
    for m in _CODE_CHUNK.finditer(code):
        chunk = m.group(0)
        if _CODE_PATH.match(chunk) or _CODE_OPTION.match(chunk) or _CODE_HYPHENATED.match(chunk):
            if all(m.end() <= a or m.start() >= b for a, b in taken):
                taken.append(m.span())
    out = [(a, b, True) for a, b in taken]
    for m in _IDENTIFIER.finditer(code):
        if all(m.end() <= a or m.start() >= b for a, b in taken):
            out.append((m.start(), m.end(), not _LOWERCASE_WORD.match(m.group(0))))
    return sorted(out)


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


def prepare_markdown(
    text: str,
) -> tuple[str, list[int], list[tuple[int, int]], list[tuple[int, int]]]:
    """Return the prepared text, the sentence starts, and the code-span ranges.

    - In a fenced code block and in a code span that holds code, each name is
      kept and returned as a name; the numbers and punctuation between the
      names become spaces. Nothing that could be a name is left out.
    - A heading marker, a table pipe, a table delimiter row, a fence line and
      the markup of a link become spaces.
    - A sentence starts at each heading, at each table cell, and at the first
      line after a blank line, a heading or a table row.
    """
    out: list[str] = []
    starts: list[int] = []
    names: list[tuple[int, int]] = []
    code_words: list[tuple[int, int]] = []
    fence: str | None = None
    new_block = True
    offset = 0
    for line in text.splitlines(keepends=True):
        here = offset
        offset += len(line)
        if fence is not None:
            stripped = line.strip()
            if stripped.startswith(fence) and set(stripped) == {fence[0]}:
                out.append(_blank(line))  # the closing fence is markup
                fence = None
                new_block = True
                continue
            # Code: each name is checked, and each is its own sentence, so the
            # sentence rules do not read a line of code as prose.
            chars = [" " if ch not in "\r\n" else ch for ch in line]
            for a, b, is_name in _words_in_code(line):
                chars[a:b] = line[a:b]
                (names if is_name else code_words).append((here + a, here + b))
                starts.append(here + a)
            out.append("".join(chars))
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
        line = _blank_backticks(line)
        for s, e in spans:
            content = line[s:e]
            if _PATH_CONTENT.match(content):
                names.append((here + s, here + e))  # one name: a file, a path
            elif " " in content or any(ch in _CODE_CHARS for ch in content):
                # Code, or literal text (a value, a message) that the author
                # cannot write again: each word in it is checked as a code
                # word or a name. The characters between the words (numbers,
                # punctuation) become spaces, so the tokenizer does not join
                # them to a word.
                found = [(s + a, s + b, n) for a, b, n in _words_in_code(content)]
                chars = list(line)
                for i in range(s, e):
                    if not any(a <= i < b for a, b, _ in found):
                        chars[i] = " "
                line = "".join(chars)
                names.extend((here + a, here + b) for a, b, n in found if n)
                code_words.extend((here + a, here + b) for a, b, n in found if not n)
            else:
                names.append((here + s, here + e))  # one name: a file, a value

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

        if new_block or _LIST_ITEM.match(line):
            starts.extend(_first_text(line, here))
            new_block = False
        out.append(line)

    result = "".join(out)
    assert len(result) == len(text)
    return result, starts, names, code_words
