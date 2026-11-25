"""Markdown headings and tables are not run together into one sentence.

A heading is one sentence. Each table cell is one sentence. The delimiter row
of a table is not text.
"""

from __future__ import annotations

import pytest

from ste100.core.analyzer import analyze

TEXT = (
    "# The places\n"
    "\n"
    "| Thing | Place |\n"
    "|---|---|\n"
    "| The issue | The repo |\n"
    "| The design | The folder |\n"
    "\n"
    "The design is in the folder. It has two parts.\n"
)


def _findings():
    return analyze(TEXT, text_type="description", markdown=True).findings


def _sentence_of(word: str, occurrence: int = 0) -> int:
    hits = [f for f in _findings() if f.evidence.get("word") == word]
    return hits[occurrence].sentence


def test_no_finding_spans_a_table_pipe_or_a_line_end() -> None:
    for f in _findings():
        span = TEXT[f.start : f.end]
        assert "|" not in span, (f.rule_id, span)
        assert "\n" not in span.strip(), (f.rule_id, span)


def test_heading_is_its_own_sentence() -> None:
    assert _sentence_of("places") != _sentence_of("Thing")


def test_each_table_cell_is_its_own_sentence() -> None:
    assert _sentence_of("Thing") != _sentence_of("Place")
    assert _sentence_of("issue") != _sentence_of("repo")
    assert _sentence_of("repo") != _sentence_of("folder", 0)


def test_paragraph_after_a_table_starts_a_new_sentence() -> None:
    assert _sentence_of("folder", 0) != _sentence_of("folder", 1)


def test_a_heading_is_not_the_topic_sentence() -> None:
    """issue-8-design.md: "## 1. Data about this file" was judged as a weak
    opening sentence."""
    text = "## 1. Data about this file\n\nThe table gives the data of this file.\n"
    result = analyze(text, text_type="description", markdown=True)
    assert [f for f in result.findings if f.rule_id == "STE-TOPIC-SENTENCE"] == []


@pytest.mark.parametrize("opening", [
    "**Issue:** [process #8](https://github.com/storybuilder-org/process/issues/8)\n"
    "**Date:** 2026-11-23. Revision 4.\n\n",
    "| Item | Data |\n|---|---|\n| This file | The design. |\n\n",
])
def test_a_label_line_or_table_is_not_the_topic_sentence(opening: str) -> None:
    text = opening + "The tool examines the text of the design.\n"
    result = analyze(text, text_type="description", markdown=True)
    assert [f for f in result.findings if f.rule_id == "STE-TOPIC-SENTENCE"] == []


def test_a_weak_first_sentence_is_still_reported_in_markdown() -> None:
    text = "## The tool\n\nIt examines the text of the design.\n"
    result = analyze(text, text_type="description", markdown=True)
    assert [f.rule_id for f in result.findings].count("STE-TOPIC-SENTENCE") == 1


def test_each_list_item_starts_a_sentence() -> None:
    """issue-8-design.md: two list items with a code span at the end of the
    first ran together into one sentence."""
    from ste100.core.markdown import prepare_markdown

    text = (
        "- The facts agree with `process` at commit `02d4b8d`.\n"
        "- The facts also agree with the fork.\n"
        "1. Open the file.\n"
        "2. Close the file.\n"
    )
    _, starts, _, _ = prepare_markdown(text)
    for line_start in (text.index("- The facts also"), text.index("2. Close")):
        assert line_start in starts


def test_delimiter_row_gives_no_finding() -> None:
    row_start = TEXT.index("|---")
    row_end = TEXT.index("\n", row_start)
    assert [f for f in _findings() if row_start <= f.start < row_end] == []
