import pytest

from app.models import PillSuggestions
from app.services.llm import select_pills, generate_fallback_pills, FALLBACK_PILLS


# ---------------------------------------------------------------------------
# Fallback pills
# ---------------------------------------------------------------------------

def test_fallback_pills_none_suggestions():
    pills = select_pills(None)
    assert pills == FALLBACK_PILLS["en"]
    assert len(pills) == 3


def test_fallback_pills_none_suggestions_indonesian():
    pills = select_pills(None, language="id")
    assert pills == FALLBACK_PILLS["id"]
    assert len(pills) == 3


def test_fallback_pills_unknown_language_defaults_to_en():
    pills = select_pills(None, language="fr")
    assert pills == FALLBACK_PILLS["en"]


def test_fallback_pills_empty_suggestions():
    """PillSuggestions with all empty lists behaves like None — falls back."""
    pills = select_pills(PillSuggestions())
    assert pills == FALLBACK_PILLS["en"]
    assert len(pills) == 3


# ---------------------------------------------------------------------------
# Priority: gap → service → industry → fallback
# ---------------------------------------------------------------------------

def test_gap_question_takes_first_slot():
    ps = PillSuggestions(
        gap_questions=["Gap Q1", "Gap Q2"],
        service_questions=["Svc Q1", "Svc Q2"],
        industry_questions=["Ind Q1"],
    )
    pills = select_pills(ps)
    assert pills[0] == "Gap Q1"


def test_service_questions_fill_after_gap():
    ps = PillSuggestions(
        gap_questions=["Gap Q1"],
        service_questions=["Svc Q1", "Svc Q2", "Svc Q3"],
    )
    pills = select_pills(ps)
    # slot 0 = gap, slots 1-2 = first two service questions
    assert pills == ["Gap Q1", "Svc Q1", "Svc Q2"]


def test_industry_question_fills_third_slot_when_services_short():
    ps = PillSuggestions(
        gap_questions=["Gap Q1"],
        service_questions=["Svc Q1"],
        industry_questions=["Ind Q1"],
    )
    pills = select_pills(ps)
    assert pills == ["Gap Q1", "Svc Q1", "Ind Q1"]


def test_fallback_fills_remaining_slots():
    """Only one gap question, no service or industry — fallback fills slots 2 and 3."""
    ps = PillSuggestions(gap_questions=["Gap Q1"])
    pills = select_pills(ps)
    assert pills[0] == "Gap Q1"
    assert len(pills) == 3
    # slots 1 and 2 must come from fallback
    for p in pills[1:]:
        assert p in FALLBACK_PILLS["en"]


def test_only_service_questions_no_gap():
    ps = PillSuggestions(service_questions=["Svc Q1", "Svc Q2", "Svc Q3"])
    pills = select_pills(ps)
    assert pills == ["Svc Q1", "Svc Q2", "Svc Q3"]


def test_only_industry_question():
    """Industry alone fills slot 0 (via fallback cascade), and fallback covers the rest."""
    ps = PillSuggestions(industry_questions=["Ind Q1"])
    pills = select_pills(ps)
    assert "Ind Q1" in pills
    assert len(pills) == 3


def test_result_capped_at_three():
    ps = PillSuggestions(
        gap_questions=["G1", "G2"],
        service_questions=["S1", "S2", "S3"],
        industry_questions=["I1"],
    )
    pills = select_pills(ps)
    assert len(pills) == 3


def test_no_duplicate_pills_when_fallback_fills():
    """Fallback items that are already in pills must not be added again."""
    # Put a fallback string as the only gap question
    gap = FALLBACK_PILLS["en"][0]
    ps = PillSuggestions(gap_questions=[gap])
    pills = select_pills(ps)
    assert pills.count(gap) == 1
    assert len(pills) == 3


def test_language_passed_to_fallback():
    ps = PillSuggestions(gap_questions=["Gap Q1"])
    pills = select_pills(ps, language="id")
    # slots filled from id fallback, not en
    for p in pills[1:]:
        assert p in FALLBACK_PILLS["id"]
