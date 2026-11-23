"""Dictionary words lost in the extraction from the PDF.

The extraction split some words at a line break and kept only the end
("netic" for "electromagnetic"), and dropped others. Each expected value
below is checked against ASD-STE100 Issue 9, on the page given.
"""

from __future__ import annotations

import pytest

from ste100.core.analyzer import analyze
from ste100.core.schema import WordStatus
from ste100.dictionary.engine import DictionaryEngine


@pytest.fixture(scope="module")
def engine() -> DictionaryEngine:
    return DictionaryEngine().load()


@pytest.mark.parametrize(
    ("word", "pos"),
    [
        ("dangerous", "adjective"),          # p207
        ("maintenance", "noun"),             # p305
        ("horizontal", "adjective"),         # p272
        ("interchangeable", "adjective"),    # p287
        ("clockwise", "adverb"),             # p191
        ("electromagnetic", "adjective"),    # p230
        ("unsatisfactory", "adjective"),     # p417
    ],
)
def test_lost_approved_word_is_present(engine: DictionaryEngine, word: str, pos: str) -> None:
    record, _ = engine.lookup_sense(word, pos)
    assert record is not None
    assert record.status is WordStatus.APPROVED


@pytest.mark.parametrize(
    ("word", "pos", "alternatives"),
    [
        ("inadvertently", "adverb", ["accidentally"]),       # p280
        ("progressively", "adverb", ["gradually"]),          # p342
        ("simultaneous", "adjective", ["at the same time"]), # p378
        ("contaminated", "adjective", ["dirty"]),            # p201
    ],
)
def test_lost_unapproved_word_is_present(
    engine: DictionaryEngine, word: str, pos: str, alternatives: list[str]
) -> None:
    record, _ = engine.lookup_sense(word, pos)
    assert record is not None
    assert record.status is WordStatus.UNAPPROVED
    assert record.alternatives == alternatives


@pytest.mark.parametrize("fragment", ["netic", "netically", "tory", "torily", "wise"])
def test_word_fragment_is_not_an_entry(engine: DictionaryEngine, fragment: str) -> None:
    assert [r for r in engine.lookup_records(fragment) if r.word == fragment] == []


def test_approved_word_from_the_pdf_example_is_not_reported() -> None:
    """The PDF's own example for BE: "ACID SOLUTIONS ARE DANGEROUS." """
    result = analyze("Acid solutions are dangerous.", text_type="description")
    assert "dangerous" not in {f.evidence.get("word") for f in result.findings}
