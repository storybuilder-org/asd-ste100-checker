"""Word-list (glossary) tools: merge an issue word list into the shared word
list, and verify a word list.

Process issue 8, design revision 4, part 10, rules 4 to 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENTRY_KEYS = ("technical_nouns", "technical_verbs")


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Word list YAML must be a mapping: {path}")
    return raw


def _entry(item: Any) -> dict[str, Any]:
    """A word-list entry as a mapping; a bare string is a word without a meaning."""
    if isinstance(item, str):
        return {"word": item}
    if isinstance(item, dict):
        return dict(item)
    raise ValueError(f"Invalid word-list entry: {item!r}")


def _meaning(entry: dict[str, Any]) -> str:
    return str(entry.get("approved_meaning") or "").strip()


def _key(word: Any) -> str:
    return str(word).strip().lower()


@dataclass
class MergeResult:
    added: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def merge(shared_path: Path, issue_path: Path) -> MergeResult:
    """Write each ``shared: true`` entry and each item of ``preferred_terms``
    of the issue word list into the shared word list.

    - An entry goes to the same list (``technical_nouns`` or
      ``technical_verbs``), without the field ``shared``.
    - The same word with the same meaning (text without spaces at the start
      and the end) is kept as it is.
    - The same word with a different meaning, or the same item of
      ``preferred_terms`` with a different value, is a conflict. With a
      conflict, no file changes.
    - The issue word list does not change. If the shared word list is not
      there, it is made.
    """
    shared = _load(shared_path)
    issue = _load(issue_path)
    result = MergeResult()

    # A word is one entry in each list: the noun "commit" and the verb
    # "commit" are two entries.
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    for key in _ENTRY_KEYS:
        shared[key] = [_entry(e) for e in shared.get(key) or []]
        for entry in shared[key]:
            existing[(key, _key(entry.get("word")))] = entry

    pending: list[tuple[str, dict[str, Any]]] = []
    for key in _ENTRY_KEYS:
        for item in issue.get(key) or []:
            entry = _entry(item)
            if not entry.pop("shared", False):
                continue
            word = (key, _key(entry.get("word")))
            have = existing.get(word)
            if have is None:
                pending.append((key, entry))
                existing[word] = entry
            elif _meaning(have) != _meaning(entry):
                result.conflicts.append(
                    f"{entry.get('word')}: shared meaning {_meaning(have)!r}, "
                    f"issue meaning {_meaning(entry)!r}"
                )

    terms = dict(shared.get("preferred_terms") or {})
    new_terms: dict[str, str] = {}
    for src, dest in (issue.get("preferred_terms") or {}).items():
        have = terms.get(src)
        if have is None:
            new_terms[src] = dest
        elif str(have).strip() != str(dest).strip():
            result.conflicts.append(
                f"preferred_terms {src}: shared value {have!r}, issue value {dest!r}"
            )

    if result.conflicts:
        return result

    for key, entry in pending:
        shared[key].append(entry)
        result.added.append(str(entry.get("word")))
    if new_terms:
        terms.update(new_terms)
        shared["preferred_terms"] = terms
        result.added.extend(f"preferred_terms {k}" for k in new_terms)
    for key in _ENTRY_KEYS:
        if not shared[key]:
            del shared[key]
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    with shared_path.open("w", encoding="utf-8", newline="\n") as fh:
        yaml.safe_dump(shared, fh, sort_keys=False, allow_unicode=True, width=1000)
    return result


def verify(path: Path) -> list[str]:
    """Errors of a word list: each entry without a meaning, and each two
    entries with the same meaning (text without spaces at the start and the
    end)."""
    data = _load(path)
    errors: list[str] = []
    seen: dict[str, str] = {}
    for key in _ENTRY_KEYS:
        for item in data.get(key) or []:
            entry = _entry(item)
            word = str(entry.get("word"))
            meaning = _meaning(entry)
            if not meaning:
                errors.append(f"{word}: no meaning")
                continue
            if meaning in seen:
                errors.append(f"{word}: same meaning as {seen[meaning]}: {meaning!r}")
            else:
                seen[meaning] = word
    return errors
