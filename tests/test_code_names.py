"""A file name or code name is one word, checked against the word files.

A name is not an English word, so it is not looked up in the STE dictionary,
and it is not split into pieces. It is looked up whole in the glossary files.
A name that no glossary lists gets one finding, for the whole name.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ste100.cli import main
from ste100.core.analyzer import analyze

NAMES = [
    "process.md",
    "lookup_sense",
    "DictionaryEngine",
    "DictionaryEngine.lookup_sense",
    "storybuilder-org/process",
    "issue-8-design.md",
    "https://github.com/storybuilder-org/process",
]


def _vocab(text: str, **kwargs):
    result = analyze(text, text_type="description", **kwargs)
    return [f for f in result.findings if f.rule_id.startswith("STE-VOCAB")]


def _glossary(tmp_path: Path, *names: str) -> str:
    path = tmp_path / "names.yaml"
    path.write_text(
        "technical_nouns:\n" + "".join(f"  - '{n}'\n" for n in names), encoding="utf-8"
    )
    return str(path)


@pytest.mark.parametrize("name", NAMES)
def test_unlisted_name_gets_one_finding_for_the_whole_name(name: str) -> None:
    text = f"The name {name} is in the code."
    hits = [f for f in _vocab(text) if text.find(name) <= f.start < text.find(name) + len(name)]
    assert len(hits) == 1
    assert text[hits[0].start : hits[0].end] == name
    assert hits[0].evidence["status"] == "name_not_in_glossary"


@pytest.mark.parametrize("name", NAMES)
def test_listed_name_gets_no_finding(tmp_path: Path, name: str) -> None:
    text = f"The name {name} is in the code."
    start = text.find(name)
    hits = [f for f in _vocab(text, glossary_path=_glossary(tmp_path, name))
            if start <= f.start < start + len(name)]
    assert hits == []


@pytest.mark.parametrize(
    ("listed", "written"),
    [
        ("rules/writing-standards.md", "writing-standards.md"),
        ("writing-standards.md", "rules/writing-standards.md"),
    ],
)
def test_path_and_its_file_name_are_one_entry(tmp_path: Path, listed: str, written: str) -> None:
    """A file is named with or without its folder; one entry covers both."""
    text = f"Read {written} first."
    hits = [f for f in _vocab(text, glossary_path=_glossary(tmp_path, listed))
            if f.evidence.get("status") == "name_not_in_glossary"]
    assert hits == []


def test_a_different_file_name_is_not_covered(tmp_path: Path) -> None:
    text = "Read rules/language.md first."
    hits = [f for f in _vocab(text, glossary_path=_glossary(tmp_path, "rules/writing-standards.md"))
            if f.evidence.get("status") == "name_not_in_glossary"]
    assert len(hits) == 1


def test_code_span_is_one_name(tmp_path: Path) -> None:
    text = "The design is in `storybuilder-miscellaneous/devdocs` now.\n"
    hits = [f for f in _vocab(text, markdown=True) if "`" in text[: f.start]
            and f.start < text.rindex("`")]
    assert len(hits) == 1
    assert text[hits[0].start : hits[0].end] == "storybuilder-miscellaneous/devdocs"


def test_two_code_spans_joined_by_a_slash_are_two_names() -> None:
    """issue-1675-design.md: `win:`/`skia:`."""
    text = "Use the `win:`/`skia:` prefixes.\n"
    names = [text[f.start : f.end] for f in _vocab(text, markdown=True)
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == ["win:", "skia:"]


def test_plain_word_in_a_code_span_is_a_name() -> None:
    """`check` in backticks is the name of something, not the verb."""
    text = "Set the value to `check` now.\n"
    hits = [f for f in _vocab(text, markdown=True) if text[f.start : f.end] == "check"]
    assert len(hits) == 1
    assert hits[0].evidence["status"] == "name_not_in_glossary"


def test_quoted_text_in_a_code_span_is_checked_word_by_word() -> None:
    """A code span with a space quotes text; it is not a name."""
    text = "Add the line `Utilize the tool now.` to the file.\n"
    findings = _vocab(text, markdown=True)
    assert "Utilize" in {f.evidence.get("word") for f in findings}
    assert not [f for f in findings if f.evidence.get("status") == "name_not_in_glossary"
                and " " in text[f.start : f.end]]


def _span_findings(text: str, **kwargs):
    start, end = text.index("`"), text.rindex("`")
    findings = analyze(text, text_type="description", markdown=True, **kwargs).findings
    return [f for f in findings if start <= f.start < end]


@pytest.mark.parametrize(
    ("code", "names"),
    [
        # issue-1675-design.md, line 221
        ("Document.GetRange(0, 1).CharacterFormat.ForegroundColor",
         ["Document", "GetRange", "CharacterFormat", "ForegroundColor"]),
        ("Close()", ["Close"]),
        ("HashSet<Guid>", ["HashSet", "Guid"]),
        ("[TestCleanup]", ["TestCleanup"]),
    ],
)
def test_each_name_in_code_is_checked(code: str, names: list[str]) -> None:
    """Code is not left out. Each name in it is checked against the glossaries;
    numbers and punctuation are not names."""
    text = f"Record the value that `{code}` returns.\n"
    found = [text[f.start : f.end] for f in _span_findings(text)]
    assert found == names
    assert all(f.evidence["status"] == "name_not_in_glossary" for f in _span_findings(text))


def test_listed_names_in_code_get_no_finding(tmp_path: Path) -> None:
    text = "Record the value that `Document.GetRange(0, 1).CharacterFormat` returns.\n"
    glossary = _glossary(tmp_path, "Document", "GetRange", "CharacterFormat")
    assert _span_findings(text, glossary_path=glossary) == []


def test_rtf_in_a_table_cell_is_checked_name_by_name() -> None:
    """issue-1675-design.md, line 241."""
    text = (
        "| Test | Input |\n"
        "|---|---|\n"
        r"| The test | `{\rtf1{\colortbl ;\red0\green0\blue0;}\cf1 a\par}` |" "\n"
    )
    start = text.index("`")
    findings = [f for f in analyze(text, text_type="description", markdown=True).findings
                if f.start >= start]
    found = [text[f.start : f.end] for f in findings]
    assert found == ["rtf1", "colortbl", "red0", "green0", "blue0", "cf1", "a", "par"]


def test_link_url_is_one_name_without_the_link_markup() -> None:
    url = "https://github.com/storybuilder-org/process/issues/8"
    text = f"Read [the issue]({url}) first.\n"
    names = [text[f.start : f.end] for f in _vocab(text, markdown=True)
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == [url]


@pytest.mark.parametrize("span", ["9500", "3377c2e", "<!--", "- [ ]"])
def test_number_or_symbols_in_a_code_span_is_not_a_name(span: str) -> None:
    text = f"Write `{span}` there.\n"
    assert [f for f in _vocab(text, markdown=True)
            if f.evidence.get("status") == "name_not_in_glossary"] == []


def test_each_name_in_a_fenced_code_block_is_checked() -> None:
    """A code block is not left out. Each name in it is checked against the
    glossaries; the fence lines are markup."""
    text = "Do the test.\n\n```csharp\nvar x = Foo.Bar(1);\n```\n"
    fence_start = text.index("```")
    findings = [f for f in analyze(text, text_type="procedure", markdown=True).findings
                if f.start >= fence_start]
    assert [text[f.start : f.end] for f in findings] == ["var", "x", "Foo", "Bar"]
    assert all(f.evidence["status"] == "name_not_in_glossary" for f in findings)


def test_listed_names_in_a_fenced_code_block_get_no_finding(tmp_path: Path) -> None:
    text = "Do the test.\n\n```\nvar x = Foo.Bar(1);\n```\n"
    fence_start = text.index("```")
    glossary = _glossary(tmp_path, "var", "x", "Foo", "Bar")
    findings = analyze(text, text_type="procedure", markdown=True,
                       glossary_path=glossary).findings
    assert [f for f in findings if f.start >= fence_start] == []


def test_abbreviation_with_periods_is_still_a_word() -> None:
    """'e.g.' is not a name. It is checked against the dictionary."""
    hits = [f for f in _vocab("Use a tool, e.g. a wrench.") if f.evidence.get("word") == "e.g."]
    assert len(hits) == 1
    assert hits[0].evidence["status"] != "name_not_in_glossary"


def test_word_pair_with_a_slash_is_not_a_name() -> None:
    for f in _vocab("Set the switch on/off and/or wait."):
        assert f.evidence.get("status") != "name_not_in_glossary"


def test_cli_treats_a_markdown_file_as_markdown(tmp_path: Path) -> None:
    path = tmp_path / "design.md"
    path.write_text("The data is in `storybuilder-miscellaneous/devdocs` now.\n",
                    encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(path), "--text-type", "description"])
    payload = json.loads(result.output)
    words = [f["evidence"].get("word") for f in payload["findings"]]
    assert "storybuilder-miscellaneous/devdocs" in words
    assert not set(words) & {"storybuilder", "miscellaneous", "devdocs"}
