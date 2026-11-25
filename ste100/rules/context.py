"""Shared rule context and typing for Tier-1 / Tier-2 / Tier-3 checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from spacy.tokens import Doc

from ste100.core.schema import Finding, TextType
from ste100.dictionary.engine import DictionaryEngine

CheckFn = Callable[[Doc, "AnalysisContext"], list[Finding]]


@dataclass
class AnalysisContext:
    """Runtime context passed to every rule check."""

    text: str
    text_type: TextType
    dictionary: DictionaryEngine
    # Token indexes inside a glossary term of more than one word.
    term_tokens: frozenset[int] = field(default_factory=frozenset)
    # Token indexes of file names, code names and URLs.
    name_tokens: frozenset[int] = field(default_factory=frozenset)
    # Token indexes of lower-case words inside code.
    code_word_tokens: frozenset[int] = field(default_factory=frozenset)
    # (start, end) of each Markdown heading line.
    heading_spans: tuple[tuple[int, int], ...] = ()
