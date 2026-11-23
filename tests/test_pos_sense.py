"""POS-sense regression tests.

The STE dictionary keys entries by part of speech and 189 headwords carry more
than one. Resolving a surface form to a single record loses that distinction in
both directions: an approved sense hides an unapproved one, and a form listed
under only one part of speech is reported against uses in another.
"""

from __future__ import annotations

import pytest

from ste100.core.analyzer import analyze
from ste100.core.fixes import apply_safe_fixes
from ste100.core.schema import Severity


def _vocab(text: str, text_type: str = "procedure"):
    result = analyze(text, text_type=text_type)
    return [f for f in result.findings if f.rule_id == "STE-VOCAB-UNAPPROVED"]


def _words(findings) -> set[str]:
    return {f.evidence.get("word") for f in findings}


def test_unapproved_verb_sense_is_not_hidden_by_approved_noun() -> None:
    """'check' is an approved noun but an unapproved verb (use 'examine')."""
    findings = [f for f in _vocab("Check the valve.") if f.severity is Severity.ERROR]
    assert "Check" in _words(findings)


def test_approved_noun_sense_still_passes() -> None:
    assert _vocab("Do a check of the valve.") == []


@pytest.mark.parametrize(
    ("text", "word"),
    [
        ("Remove the cover.", "cover"),
        ("Disconnect the power supply.", "power"),
    ],
)
def test_noun_use_of_verb_only_entry_is_not_reported(text: str, word: str) -> None:
    """The unapproved verb sense must not be reported against noun usage."""
    assert word not in _words(_vocab(text))


@pytest.mark.parametrize(
    ("text", "word"),
    [
        # Both were edge cases E13/E34, which asserted these were clean. The
        # POS-blind lookup resolved each form to its other, approved sense.
        ("Switch the unit to ON.", "Switch"),   # switch (v) -> "set"
        ("Calibrate the sensor before use.", "use"),  # use (n) -> "operation"
    ],
)
def test_unapproved_sense_is_reported_despite_approved_homograph(
    text: str, word: str
) -> None:
    findings = [f for f in _vocab(text) if f.severity is Severity.ERROR]
    assert word in _words(findings)


def test_sense_absent_from_dictionary_is_silent_when_form_is_approved() -> None:
    """POS coverage is incomplete; a missing sense is not evidence of disapproval.

    'first' is recorded only as an adverb, and is used here as an adjective.
    """
    assert "first" not in _words(_vocab("Remove the first bolt."))


def test_pos_mismatch_respects_a_second_approved_sense() -> None:
    """'set' is approved as both noun and verb; the verb use is not a clash."""
    findings = analyze("Set the switch to ON.", text_type="procedure").findings
    assert [f for f in findings if f.rule_id == "STE-POS-MISMATCH"] == []


def test_clean_procedure_has_no_errors() -> None:
    text = "1. Remove the cover.\n2. Disconnect the power supply.\n"
    assert [f for f in analyze(text, text_type="procedure").findings
            if f.severity is Severity.ERROR] == []


def test_safe_fixes_keep_the_unambiguous_case() -> None:
    result = apply_safe_fixes("Utilize the tool.")
    assert result["fixed"] == "Use the tool."
    assert result["original"] == "Utilize the tool."
    assert result["diff"]


@pytest.mark.parametrize(
    "text",
    [
        "Disconnect the power supply.",          # power (n) -> "supply supply"
        "Do this in the event that it fails.",   # event (n) -> "in the if that"
    ],
)
def test_safe_fixes_do_not_corrupt_text(text: str) -> None:
    """A replacement must never fire on a sense the dictionary does not cover."""
    result = apply_safe_fixes(text)
    assert result["fixed"] == text
    assert result["replacements_applied"] == []


def test_phrase_derived_alternative_is_not_applied_word_for_word() -> None:
    """'event' -> 'if' comes from "in the event that"; 'if' is a conjunction."""
    from ste100.dictionary.engine import get_default_engine

    engine = get_default_engine()
    assert engine.safe_replacement_for("event", "noun") is None
    assert engine.safe_replacement_for("utilize", "verb") == "use"


def test_lookup_payload_reports_every_sense() -> None:
    """A single-sense payload says 'check: approved' and hides the verb."""
    from ste100.dictionary.engine import get_default_engine

    engine = get_default_engine()
    payload = engine.lookup_payload("check")
    senses = {s["part_of_speech"]: s["status"] for s in payload["senses"]}
    assert senses == {"noun": "approved", "verb": "unapproved"}

    # Single-sense entries stay as they were — no empty key added.
    assert "senses" not in engine.lookup_payload("remove")


def test_dictionary_pos_maps_spacy_tags() -> None:
    from ste100.dictionary.engine import dictionary_pos

    assert dictionary_pos("NOUN") == "noun"
    assert dictionary_pos("AUX") == "verb"
    assert dictionary_pos("SCONJ") == "conjunction"
    assert dictionary_pos(None) is None
    assert dictionary_pos("X") is None


def test_lookup_sense_reports_form_known() -> None:
    from ste100.dictionary.engine import get_default_engine

    engine = get_default_engine()
    # 'first' is recorded only as an adverb: the form is known, the sense is not.
    record, form_known = engine.lookup_sense("first", "noun")
    assert record is None and form_known is True

    record, form_known = engine.lookup_sense("first", "adverb")
    assert record is not None and form_known is True

    # Both senses of 'cover' are recorded, and each resolves to its own record.
    assert engine.lookup_sense("cover", "noun")[0].part_of_speech == "noun"
    assert engine.lookup_sense("cover", "verb")[0].part_of_speech == "verb"

    record, form_known = engine.lookup_sense("zzzznotaword", "noun")
    assert record is None and form_known is False
