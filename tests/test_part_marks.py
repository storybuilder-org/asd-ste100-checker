"""Part marks, the text hash and the checker commit (process issue 8, design
revision 4, part 11, rules 1 to 6)."""

from __future__ import annotations

import hashlib
import json

from click.testing import CliRunner

from ste100.cli import main
from ste100.core.analyzer import analyze

DESIGN = (
    "# A design\n"                                   # 1
    "\n"                                              # 2
    "<!-- ste100: plain-english -->\n"                # 3
    "\n"                                              # 4
    "## Summary\n"                                    # 5
    "\n"                                              # 6
    "We utilize lots of stuff here, basically.\n"     # 7
    "\n"                                              # 8
    "<!-- ste100: description -->\n"                  # 9
    "\n"                                              # 10
    "The tool examines the text.\n"                   # 11
    "\n"                                              # 12
    "<!-- ste100: procedure -->\n"                    # 13
    "\n"                                              # 14
    "1. Utilize the tool.\n"                          # 15
)


def _parts(result):
    return [(p["type"], p["first_line"], p["last_line"], p["checked"]) for p in result.parts]


def test_parts_are_listed_with_type_lines_and_checked() -> None:
    result = analyze(DESIGN, text_type="description", markdown=True)
    assert _parts(result) == [
        ("description", 1, 2, True),
        ("plain-english", 3, 8, False),
        ("description", 9, 12, True),
        ("procedure", 13, 15, True),
    ]


def test_plain_english_part_gets_no_finding() -> None:
    result = analyze(DESIGN, text_type="description", markdown=True)
    summary_start = DESIGN.index("We utilize")
    summary_end = DESIGN.index("<!-- ste100: description -->")
    assert [f for f in result.findings if summary_start <= f.start < summary_end] == []


LONG = ("the tool examines the text of the file and then the tool shows each error "
        "of the text on the screen of the computer")  # 22 words


def test_each_part_gets_the_rules_of_its_type() -> None:
    """A sentence of 22 words is correct in a description part (maximum 25)
    and too long in a procedure part (maximum 20)."""
    text = (
        "<!-- ste100: description -->\n\n"
        f"{LONG[0].upper()}{LONG[1:]}.\n\n"
        "<!-- ste100: procedure -->\n\n"
        "1. Examine the text of the file and then show each error of the text "
        "on the screen of the computer with the tool.\n"  # 23 words
    )
    result = analyze(text, text_type="description", markdown=True)
    long_hits = [f for f in result.findings if f.rule_id == "STE-SENTENCE-LENGTH"]
    assert len(long_hits) == 1
    assert long_hits[0].start > text.index("<!-- ste100: procedure -->")


def test_text_before_the_first_mark_has_the_option_type() -> None:
    result = analyze(DESIGN, text_type="procedure", markdown=True)
    assert _parts(result)[0] == ("procedure", 1, 2, True)


def test_text_without_marks_is_one_part() -> None:
    text = "The tool examines the text.\nIt is clean.\n"
    result = analyze(text, text_type="description", markdown=True)
    assert _parts(result) == [("description", 1, 2, True)]


def test_source_sha256_is_the_hash_of_the_text_with_lf() -> None:
    text = "The tool examines the text.\r\nIt is clean.\r\n"
    result = analyze(text, text_type="description", markdown=True)
    expected = hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    assert result.source_sha256 == expected


def test_checker_commit_is_a_commit_or_null() -> None:
    """An editable install has no commit in direct_url.json; the value is then
    null. An install from git gives a 40-character commit."""
    result = analyze("The tool examines the text.\n", text_type="description")
    commit = result.checker_commit
    assert commit is None or (len(commit) == 40 and all(c in "0123456789abcdef" for c in commit))


def test_cli_output_has_parts_hash_and_commit(tmp_path) -> None:
    path = tmp_path / "design.md"
    path.write_text(DESIGN, encoding="utf-8")
    result = CliRunner().invoke(main, ["check", str(path), "--text-type", "description"])
    payload = json.loads(result.output)
    assert [p["type"] for p in payload["parts"]] == [
        "description", "plain-english", "description", "procedure"]
    assert "source_sha256" in payload
    assert "checker_commit" in payload
