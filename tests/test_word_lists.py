"""The field `shared` and the commands `ste100 glossary merge` and
`ste100 glossary verify` (process issue 8, design revision 4, part 11,
rules 7 to 9, and part 10, rules 4 to 8)."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from ste100.cli import main
from ste100.core.analyzer import analyze


def _write(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _merge(shared: Path, issue: Path):
    return CliRunner().invoke(main, ["glossary", "merge", str(shared), str(issue)])


def _verify(path: Path):
    return CliRunner().invoke(main, ["glossary", "verify", str(path)])


# --- rule 7: the field shared --------------------------------------------

def test_shared_field_is_accepted_and_has_no_effect(tmp_path: Path) -> None:
    glossary = _write(tmp_path / "g.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A Git repository.", "shared": True},
    ]})
    result = analyze("Open the repo.", text_type="procedure", glossary_path=str(glossary))
    assert "repo" not in {f.evidence.get("word") for f in result.findings}


# --- rule 8: glossary merge ------------------------------------------------

def test_merge_writes_each_shared_entry_without_the_field(tmp_path: Path) -> None:
    shared = _write(tmp_path / "shared.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A Git repository."}]})
    issue = _write(tmp_path / "issue.yaml", {
        "technical_nouns": [
            {"word": "branch", "approved_meaning": "A named line of commits.", "shared": True},
            {"word": "LogService", "approved_meaning": "The logging class."},
        ],
        "technical_verbs": [
            {"word": "rebase", "approved_meaning": "To move commits onto a new base.", "shared": True},
        ],
    })
    result = _merge(shared, issue)
    assert result.exit_code == 0, result.output
    data = _read(shared)
    nouns = {e["word"]: e for e in data["technical_nouns"]}
    assert set(nouns) == {"repo", "branch"}
    assert "shared" not in nouns["branch"]
    assert [e["word"] for e in data["technical_verbs"]] == ["rebase"]


def test_merge_does_not_change_the_issue_list(tmp_path: Path) -> None:
    shared = _write(tmp_path / "shared.yaml", {"technical_nouns": []})
    issue = _write(tmp_path / "issue.yaml", {"technical_nouns": [
        {"word": "branch", "approved_meaning": "A named line of commits.", "shared": True}]})
    before = issue.read_text(encoding="utf-8")
    assert _merge(shared, issue).exit_code == 0
    assert issue.read_text(encoding="utf-8") == before


def test_merge_keeps_an_entry_with_the_same_meaning(tmp_path: Path) -> None:
    shared = _write(tmp_path / "shared.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A Git repository."}]})
    issue = _write(tmp_path / "issue.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "  A Git repository. ", "shared": True}]})
    assert _merge(shared, issue).exit_code == 0
    assert len(_read(shared)["technical_nouns"]) == 1


def test_merge_stops_on_a_different_meaning_and_changes_no_file(tmp_path: Path) -> None:
    shared = _write(tmp_path / "shared.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A Git repository."}]})
    issue = _write(tmp_path / "issue.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A storage place.", "shared": True},
        {"word": "branch", "approved_meaning": "A named line of commits.", "shared": True}]})
    before = shared.read_text(encoding="utf-8")
    result = _merge(shared, issue)
    assert result.exit_code == 1
    assert "repo" in result.output
    assert shared.read_text(encoding="utf-8") == before


def test_merge_copies_preferred_terms_and_stops_on_a_different_value(tmp_path: Path) -> None:
    shared = _write(tmp_path / "shared.yaml", {"preferred_terms": {"antagonist": "opposition"}})
    issue = _write(tmp_path / "issue.yaml", {"preferred_terms": {"villain": "opposition"}})
    assert _merge(shared, issue).exit_code == 0
    assert _read(shared)["preferred_terms"] == {"antagonist": "opposition", "villain": "opposition"}

    clash = _write(tmp_path / "clash.yaml", {"preferred_terms": {"antagonist": "enemy"}})
    result = _merge(shared, clash)
    assert result.exit_code == 1
    assert "antagonist" in result.output


def test_merge_keeps_a_noun_and_a_verb_of_the_same_word(tmp_path: Path) -> None:
    """The noun "commit" and the verb "commit" are two entries, in two lists.
    Found when the first shared word list was built."""
    shared = tmp_path / "shared.yaml"
    issue = _write(tmp_path / "issue.yaml", {
        "technical_nouns": [{"word": "commit", "approved_meaning": "One recorded set of changes.",
                             "shared": True}],
        "technical_verbs": [{"word": "commit", "approved_meaning": "To record a set of changes.",
                             "shared": True}],
    })
    result = _merge(shared, issue)
    assert result.exit_code == 0, result.output
    data = _read(shared)
    assert [e["word"] for e in data["technical_nouns"]] == ["commit"]
    assert [e["word"] for e in data["technical_verbs"]] == ["commit"]


def test_merge_makes_the_shared_list_if_it_is_not_there(tmp_path: Path) -> None:
    shared = tmp_path / "shared.yaml"
    issue = _write(tmp_path / "issue.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A Git repository.", "shared": True}]})
    assert _merge(shared, issue).exit_code == 0
    assert [e["word"] for e in _read(shared)["technical_nouns"]] == ["repo"]


# --- rule 9: glossary verify -----------------------------------------------

def test_verify_accepts_a_correct_list(tmp_path: Path) -> None:
    path = _write(tmp_path / "g.yaml", {"technical_nouns": [
        {"word": "repo", "approved_meaning": "A Git repository."},
        {"word": "branch", "approved_meaning": "A named line of commits."}]})
    assert _verify(path).exit_code == 0


def test_verify_finds_an_entry_without_a_meaning(tmp_path: Path) -> None:
    path = _write(tmp_path / "g.yaml", {"technical_nouns": [
        "repo", {"word": "branch", "approved_meaning": " "}]})
    result = _verify(path)
    assert result.exit_code == 1
    assert "repo" in result.output and "branch" in result.output


def test_verify_finds_two_entries_with_the_same_meaning(tmp_path: Path) -> None:
    path = _write(tmp_path / "g.yaml", {
        "technical_nouns": [{"word": "user", "approved_meaning": "Technical noun (rule 1.5)."}],
        "technical_verbs": [{"word": "enable", "approved_meaning": "Technical noun (rule 1.5). "}],
    })
    result = _verify(path)
    assert result.exit_code == 1
    assert "user" in result.output and "enable" in result.output
