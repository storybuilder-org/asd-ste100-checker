"""More than one glossary file per run, and glossary terms of more than one word."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ste100.cli import main
from ste100.core.analyzer import analyze


def _write(path: Path, *nouns: str) -> Path:
    path.write_text(
        "technical_nouns:\n" + "".join(f"  - {n}\n" for n in nouns), encoding="utf-8"
    )
    return path


def _words(result) -> set[str]:
    return {f.evidence.get("word") for f in result.findings}


@pytest.fixture
def shared(tmp_path: Path) -> Path:
    return _write(tmp_path / "shared.yaml", "pull request", "code span", "repo")


@pytest.fixture
def issue(tmp_path: Path) -> Path:
    return _write(tmp_path / "issue.yaml", "DesignChecker", "devdocs")


def test_analyze_merges_every_glossary(shared: Path, issue: Path) -> None:
    result = analyze(
        "Open the repo and the devdocs folder.",
        text_type="procedure",
        glossary_path=[str(shared), str(issue)],
    )
    assert not _words(result) & {"repo", "devdocs"}


@pytest.mark.parametrize(
    "text",
    [
        "Open the pull request.",
        "Merge the pull requests.",
        "Remove the code span.",
    ],
)
def test_multi_word_term_is_accepted(shared: Path, text: str) -> None:
    result = analyze(text, text_type="procedure", glossary_path=str(shared))
    assert not _words(result) & {"pull", "request", "requests", "code", "span"}


def test_words_of_a_term_are_still_checked_alone(shared: Path) -> None:
    """'span' is accepted inside 'code span', not by itself."""
    result = analyze("Remove the span.", text_type="procedure", glossary_path=str(shared))
    assert "span" in _words(result)


def test_cli_takes_more_than_one_glossary(shared: Path, issue: Path) -> None:
    result = CliRunner().invoke(
        main,
        ["check", "--text-type", "procedure",
         "--glossary", str(shared), "--glossary", str(issue)],
        input="Open the repo and the devdocs folder.\n",
    )
    payload = json.loads(result.output)
    words = {f["evidence"].get("word") for f in payload["findings"]}
    assert not words & {"repo", "devdocs"}
