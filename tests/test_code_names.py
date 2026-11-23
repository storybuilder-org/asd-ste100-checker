"""Code names and file names are not vocabulary.

A name from code or a file path is not an English word, so the vocabulary
rules must not report it, and must not split it and report the pieces.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from ste100.cli import main
from ste100.core.analyzer import analyze


def _vocab_words(text: str, **kwargs) -> set[str]:
    result = analyze(text, text_type="description", **kwargs)
    return {
        f.evidence.get("word")
        for f in result.findings
        if f.rule_id.startswith("STE-VOCAB")
    }


@pytest.mark.parametrize(
    "name",
    [
        "process.md",
        "lookup_sense",
        "DictionaryEngine",
        "DictionaryEngine.lookup_sense",
    ],
)
def test_bare_code_name_is_not_reported(name: str) -> None:
    assert name not in _vocab_words(f"The name {name} is in the code.")


def test_abbreviation_with_periods_is_still_reported() -> None:
    """'e.g.' is not a code name. A dotted name does not end in a period."""
    assert "e.g." in _vocab_words("Use a tool, e.g. a wrench.")


def test_code_span_is_not_reported_or_split() -> None:
    text = "The design is in `storybuilder-miscellaneous/devdocs` now.\n"
    words = _vocab_words(text, markdown=True)
    assert not words & {"storybuilder", "miscellaneous", "devdocs"}


def test_fenced_code_block_is_not_checked() -> None:
    text = "Do the test.\n\n```\nutilize_everything --now\nfoo bar baz\n```\n"
    result = analyze(text, text_type="procedure", markdown=True)
    fence_start = text.index("```")
    assert [f for f in result.findings if f.start >= fence_start] == []


def test_offsets_after_a_code_span_point_into_the_original_text() -> None:
    text = "Open `a_file.md` and utilize the tool.\n"
    result = analyze(text, text_type="procedure", markdown=True)
    hits = [f for f in result.findings if f.evidence.get("word") == "utilize"]
    assert len(hits) == 1
    assert text[hits[0].start : hits[0].end] == "utilize"


def test_cli_treats_a_markdown_file_as_markdown(tmp_path) -> None:
    path = tmp_path / "design.md"
    path.write_text("The data is in `storybuilder-miscellaneous/devdocs` now.\n",
                    encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(path), "--text-type", "description"])
    payload = json.loads(result.output)
    words = {f["evidence"].get("word") for f in payload["findings"]}
    assert not words & {"storybuilder", "miscellaneous", "devdocs"}
