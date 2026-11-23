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


@pytest.mark.parametrize(
    "written",
    ["StoryCADLib/Models/Windowing.cs:185", "Windowing.cs:252-260"],
)
def test_a_line_reference_is_covered_by_the_file_entry(tmp_path: Path, written: str) -> None:
    """issue-1638-design.md names files with a line number after a colon."""
    text = f"Read {written} first."
    hits = [f for f in _vocab(text, glossary_path=_glossary(tmp_path, "StoryCADLib/Models/Windowing.cs"))
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


@pytest.mark.parametrize("path", [r"D:\dev\src\CLAUDE.md", "~/.claude/CLAUDE.md"])
def test_path_in_a_code_span_is_one_name(path: str) -> None:
    """issue-10-design.md, item 9."""
    text = f"The file `{path}` stays on the computer.\n"
    names = [text[f.start : f.end] for f in _vocab(text, markdown=True)
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == [path]


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


def test_lowercase_word_in_code_is_checked_as_a_word() -> None:
    """issue-1638-design.md: `File {filePath} is unavailable.` The lower-case
    words are English and are checked against the dictionary; 'File' and
    'filePath' are names."""
    text = "Line 415 writes `File {filePath} is unavailable.` at the start.\n"
    findings = _span_findings(text)
    names = [text[f.start : f.end] for f in findings
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == ["File", "filePath"]
    assert "is" not in [text[f.start : f.end] for f in findings]


def test_unapproved_lowercase_word_in_code_is_reported_as_a_word() -> None:
    text = "The comment says `// utilize {x} here`.\n"
    hits = [f for f in _span_findings(text) if text[f.start : f.end] == "utilize"]
    assert len(hits) == 1
    assert hits[0].evidence["status"] != "name_not_in_glossary"


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
    names = [text[f.start : f.end] for f in findings
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == ["rtf1", "red0", "green0", "blue0", "cf1"]
    # 'a' is an approved English word.
    assert "a" not in [text[f.start : f.end] for f in findings]


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
    names = [text[f.start : f.end] for f in findings
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == ["Foo", "Bar"]
    # 'var' is lower case: it is checked as a word, and it is not in the dictionary.
    assert "var" in [text[f.start : f.end] for f in findings]


@pytest.mark.parametrize(
    ("code", "name"),
    [
        ('uv tool install "git+https://github.com/storybuilder-org/asd-ste100-checker"',
         "https://github.com/storybuilder-org/asd-ste100-checker"),
        ("ste100 check --glossary process/word-lists/shared.yaml",
         "process/word-lists/shared.yaml"),
        (r"cd D:\dev\src\process", r"D:\dev\src\process"),
    ],
)
def test_url_or_path_in_code_is_one_name(code: str, name: str) -> None:
    """A URL or a path inside code is one name, not cut into its words."""
    for text in (f"Run this.\n\n```\n{code}\n```\n", f"Run `{code}` now.\n"):
        names = [text[f.start : f.end] for f in _vocab(text, markdown=True)
                 if f.evidence.get("status") == "name_not_in_glossary"]
        assert name in names, text
        assert not any(n != name and n in name for n in names), (text, names)


def test_placeholder_in_a_path_is_part_of_the_path() -> None:
    """issue-8-design.md: `devdocs/issue-<n>-design-glossary.yaml`."""
    name = "devdocs/issue-<n>-design-glossary.yaml"
    text = f"The list is `{name}` now.\n"
    names = [text[f.start : f.end] for f in _vocab(text, markdown=True)
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert names == [name]


@pytest.mark.parametrize(("code", "names"), [
    ("node --test", ["--test"]),
    ("uv tool dir --bin", ["--bin"]),
])
def test_command_with_an_option_in_a_code_span_is_code(code: str, names: list[str]) -> None:
    """A code span with an option (-x or --name) is a command, not quoted text."""
    text = f"Give the command `{code}` now.\n"
    found = [text[f.start : f.end] for f in _vocab(text, markdown=True)
             if f.evidence.get("status") == "name_not_in_glossary"]
    assert found == names


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
