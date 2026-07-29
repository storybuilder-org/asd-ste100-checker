"""Safe 1:1 synonym fixes and shared formatting helpers."""

from __future__ import annotations

import difflib
from typing import Any

from ste100.dictionary.engine import (
    DictionaryEngine,
    is_non_vocabulary_token,
    resolve_engine,
)
from ste100.rules.spacy_util import token_pos_candidates


def _preserve_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper() and original[1:].islower():
        return replacement[:1].upper() + replacement[1:].lower()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_safe_fixes(
    text: str,
    glossary_path: str | None = None,
    *,
    dictionary: DictionaryEngine | None = None,
) -> dict[str, Any]:
    """Apply unambiguous 1:1 synonym replacements; return text + unified diff.

    Replacement is decided per token from the part of speech spaCy assigns it,
    not from the surface form. A context-free pass cannot tell the approved
    noun ``power supply`` from the unapproved verb ``to power``, and rewrites
    the former into ``supply supply``.
    """
    from ste100.core.analyzer import get_nlp

    engine = resolve_engine(dictionary, glossary_path)
    engine.ensure_loaded()

    doc = get_nlp()(text)
    replacements_applied: list[dict[str, str | int]] = []
    pieces: list[str] = []
    cursor = 0

    for token in doc:
        original = token.text
        if token.is_space or token.is_punct or is_non_vocabulary_token(original):
            continue
        dest = engine.safe_replacement_for(original, token_pos_candidates(token))
        if dest is None:
            continue
        fixed = _preserve_case(original, dest)
        if fixed == original:
            continue
        start = token.idx
        end = start + len(original)
        pieces.append(text[cursor:start])
        pieces.append(fixed)
        cursor = end
        replacements_applied.append(
            {"from": original, "to": fixed, "start": start, "end": end}
        )

    pieces.append(text[cursor:])
    fixed_text = "".join(pieces)
    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            fixed_text.splitlines(keepends=True),
            fromfile="original",
            tofile="fixed",
        )
    )
    return {
        "original": text,
        "fixed": fixed_text,
        "diff": diff,
        "replacements_applied": replacements_applied,
    }
