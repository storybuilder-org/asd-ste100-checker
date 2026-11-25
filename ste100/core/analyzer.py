"""Analyzer: orchestrates rules, detects text type, produces AnalysisResult."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from typing import Never

import spacy
from spacy.language import Language
from spacy.tokens import Doc

from ste100.core.markdown import prepare_markdown
from ste100.core.schema import AnalysisResult, Finding, Severity, TextType
from ste100.dictionary.engine import DictionaryEngine, is_code_name, resolve_engine
from ste100.rules.context import AnalysisContext
from ste100.rules.registry import get_all_checks
from ste100.rules.spacy_util import content_tokens, is_imperative_span

DEFAULT_SPACY_MODEL = "en_core_web_sm"
_ENV_SPACY_MODEL = "STE100_SPACY_MODEL"

_NLP: Language | None = None
_NLP_MODEL: str | None = None
_SPACY_MODEL_OVERRIDE: str | None = None

_NUMBERED_STEP = re.compile(
    r"(?m)^\s*(?:step\s+)?\d+[.)]\s+\S",
    re.IGNORECASE,
)


def get_spacy_model_name() -> str:
    """Resolve the spaCy model: override, then env, then default."""
    if _SPACY_MODEL_OVERRIDE:
        return _SPACY_MODEL_OVERRIDE
    env_value = os.environ.get(_ENV_SPACY_MODEL, "").strip()
    if env_value:
        return env_value
    return DEFAULT_SPACY_MODEL


def set_spacy_model(name: str | None) -> None:
    """Set a process-wide spaCy model override and clear the cached pipeline.

    Pass ``None`` to clear the override (env / default apply again).
    """
    global _SPACY_MODEL_OVERRIDE
    _SPACY_MODEL_OVERRIDE = name.strip() if name else None
    clear_nlp()


def clear_nlp() -> None:
    """Drop the cached spaCy pipeline (tests / model switches)."""
    global _NLP, _NLP_MODEL
    _NLP = None
    _NLP_MODEL = None


def get_nlp(model: str | None = None) -> Language:
    """Lazy singleton spaCy pipeline.

    Model resolution order when ``model`` is omitted:
    ``set_spacy_model`` override → ``STE100_SPACY_MODEL`` env → ``en_core_web_sm``.
    """
    global _NLP, _NLP_MODEL
    requested = (model.strip() if model else None) or get_spacy_model_name()
    if _NLP is None or _NLP_MODEL != requested:
        _NLP = spacy.load(requested)
        _NLP_MODEL = requested
    return _NLP


def detect_text_type(doc: Doc, text: str) -> TextType:
    """Heuristic: numbered steps / imperative density -> PROCEDURE, else DESCRIPTION."""
    if _NUMBERED_STEP.search(text):
        return TextType.PROCEDURE

    sents = list(doc.sents)
    if not sents:
        return TextType.DESCRIPTION

    imperative_sents = 0
    total_words = 0
    for sent in sents:
        tokens = content_tokens(sent)
        total_words += len(tokens)
        if is_imperative_span(sent):
            imperative_sents += 1

    ratio = imperative_sents / len(sents)
    avg_words = total_words / len(sents)
    # Procedures: dense imperatives that look like steps (short / multi-sentence).
    if ratio >= 0.5 and (len(sents) >= 2 or avg_words <= 20):
        return TextType.PROCEDURE
    return TextType.DESCRIPTION


def _resolve_text_type(requested: TextType, doc: Doc, text: str) -> TextType:
    if requested is TextType.AUTO:
        return detect_text_type(doc, text)
    if requested is TextType.PROCEDURE:
        return TextType.PROCEDURE
    if requested is TextType.DESCRIPTION:
        return TextType.DESCRIPTION
    _exhaustive: Never = requested
    raise AssertionError(f"Unhandled TextType: {_exhaustive}")


def _parse_text_type(text_type: TextType | str) -> TextType:
    if isinstance(text_type, TextType):
        return text_type
    normalized = text_type.strip().lower()
    for member in TextType:
        if member.value == normalized:
            return member
    raise ValueError(
        f"Invalid text_type {text_type!r}; expected one of "
        f"{', '.join(t.value for t in TextType)}"
    )


def _summary(findings: list[Finding]) -> dict[str, int]:
    counts = {
        "total": len(findings),
        "error": 0,
        "warning": 0,
        "info": 0,
    }
    for finding in findings:
        sev = finding.severity
        if sev is Severity.ERROR:
            counts["error"] += 1
        elif sev is Severity.WARNING:
            counts["warning"] += 1
        elif sev is Severity.INFO:
            counts["info"] += 1
        else:
            _exhaustive: Never = sev
            raise AssertionError(f"Unhandled Severity: {_exhaustive}")
    return counts


_URL = re.compile(r"https?://[^\s<>()`]+[^\s<>()`.,;:!?]")
# A path: word characters joined by slashes, with hyphens or periods inside.
_PATH = re.compile(r"(?<![\w./-])[\w.-]*\w/[\w./-]*\w")


def _name_spans(text: str, code_spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Character ranges that are each one name: code spans, URLs, and paths.

    The tokenizer splits a word at a hyphen or a slash, so these ranges are
    merged back into one token before the pipeline runs.
    """
    candidates = list(code_spans)
    candidates += [m.span() for m in _URL.finditer(text)]
    candidates += [m.span() for m in _PATH.finditer(text) if is_code_name(m.group(0))]
    out: list[tuple[int, int]] = []
    for start, end in candidates:  # earlier kinds win an overlap
        if all(end <= s or start >= e for s, e in out):
            out.append((start, end))
    return sorted(out)


def _parse(
    nlp: Language,
    text: str,
    starts: list[int],
    names: list[tuple[int, int]],
) -> tuple[Doc, frozenset[int]]:
    """Run the pipeline with each name as one token and a sentence start fixed
    at each offset. Return the doc and the indexes of the name tokens.

    The dependency parser keeps sentence starts that are set before it runs.
    """
    doc = nlp.make_doc(text)
    with doc.retokenize() as retokenizer:
        for start, end in names:
            span = doc.char_span(start, end, alignment_mode="expand")
            if span is not None and len(span) > 1:
                retokenizer.merge(span)
    wanted = set(starts)
    for token in doc:
        if token.idx in wanted and token.i > 0:
            token.is_sent_start = True
    for _name, proc in nlp.pipeline:
        doc = proc(doc)
    name_starts = {start for start, _ in names}
    name_tokens = frozenset(
        t.i for t in doc if t.idx in name_starts or is_code_name(t.text)
    )
    return doc, name_tokens


def analyze(
    text: str,
    text_type: TextType | str = TextType.AUTO,
    glossary_path: str | Sequence[str] | None = None,
    *,
    dictionary: DictionaryEngine | None = None,
    markdown: bool = False,
) -> AnalysisResult:
    """Run all registered Tier-1/Tier-2/Tier-3 rules and return an AnalysisResult.

    A file name, code name or URL is one token, checked against the
    glossaries (see :func:`ste100.dictionary.engine.is_code_name`). With
    ``markdown``, each name in code is checked against the glossaries, and
    each heading and table cell is a sentence (see :mod:`ste100.core.markdown`).
    Finding offsets refer to ``text``.
    """
    requested = _parse_text_type(text_type)
    nlp = get_nlp()
    starts: list[int] = []
    code_spans: list[tuple[int, int]] = []
    code_words: list[tuple[int, int]] = []
    if markdown:
        text, starts, code_spans, code_words = prepare_markdown(text)
    doc, name_tokens = _parse(nlp, text, starts, _name_spans(text, code_spans))
    code_word_starts = {start for start, _ in code_words}
    code_word_tokens = frozenset(t.i for t in doc if t.idx in code_word_starts)

    engine = resolve_engine(dictionary, glossary_path)

    resolved = _resolve_text_type(requested, doc, text)
    context = AnalysisContext(
        text=text,
        text_type=resolved,
        dictionary=engine,
        term_tokens=frozenset(engine.multiword_term_tokens([t.text for t in doc])),
        name_tokens=name_tokens,
        code_word_tokens=code_word_tokens,
    )

    findings: list[Finding] = []
    for check in get_all_checks():
        findings.extend(check(doc, context))

    if markdown:
        # A blanked pipe or marker is whitespace in ``text`` but not in the
        # original, so a span that ends in whitespace must not cover it.
        for finding in findings:
            while finding.end > finding.start and text[finding.end - 1].isspace():
                finding.end -= 1
            while finding.start < finding.end and text[finding.start].isspace():
                finding.start += 1

    findings.sort(key=lambda f: (f.start, f.end, f.rule_id))

    summary = _summary(findings)
    compliant = summary["error"] == 0
    return AnalysisResult(
        text_type=resolved,
        compliant=compliant,
        findings=findings,
        summary=summary,
    )
