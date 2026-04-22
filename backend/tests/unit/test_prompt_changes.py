"""
Unit tests for prompt-related changes:
- _notion_quality_label()
- generate_lead_brief() derivation logic (quality_score, scope_match, red_flags)
- build_chat_system_prompt() out_of_scope block rendering
- _profile_from_partial() out_of_scope handling
"""
import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.models import CompanyProfile, Session, Message
from app.services.notion import _notion_quality_label
from app.services.llm import build_chat_system_prompt, _profile_from_partial


# ---------------------------------------------------------------------------
# _notion_quality_label
# ---------------------------------------------------------------------------

def test_notion_label_qualified_maps_to_high():
    assert _notion_quality_label({"qualification": "qualified"}) == "High"


def test_notion_label_out_of_scope_maps_to_low():
    assert _notion_quality_label({"qualification": "out_of_scope"}) == "Low"


def test_notion_label_suspicious_maps_to_low():
    assert _notion_quality_label({"qualification": "suspicious"}) == "Low"


def test_notion_label_unclear_maps_to_medium():
    assert _notion_quality_label({"qualification": "unclear"}) == "Medium"


def test_notion_label_falls_back_to_quality_score_when_no_qualification():
    assert _notion_quality_label({"quality_score": "high"}) == "High"
    assert _notion_quality_label({"quality_score": "low"}) == "Low"


def test_notion_label_default_medium_when_both_missing():
    assert _notion_quality_label({}) == "Medium"


def test_notion_label_qualification_takes_precedence_over_quality_score():
    data = {"qualification": "suspicious", "quality_score": "high"}
    assert _notion_quality_label(data) == "Low"


# ---------------------------------------------------------------------------
# Helpers shared by generate_lead_brief tests
# ---------------------------------------------------------------------------

def _make_brief_response(overrides: dict) -> dict:
    base = {
        "who": "Test visitor",
        "need": "Test need",
        "scope_match": True,
        "qualification": "qualified",
        "qualification_reason": "Visitor showed clear interest.",
        "signals": "High urgency",
        "open_questions": "Budget?",
        "suggested_approach": "Follow up via email.",
        "red_flags": [],
        "contact": {"email": None, "phone": None, "whatsapp": None},
    }
    base.update(overrides)
    return base


def _make_session() -> Session:
    return Session(
        session_id="test-session",
        kb_id="test-kb",
        messages=[
            Message(role="user", text="Hello", timestamp=1000),
            Message(role="assistant", text="Hi there!", timestamp=1001),
        ],
        created_at=1000,
    )


def _run_brief(response_data: dict) -> object:
    from app.services.llm import generate_lead_brief
    session = _make_session()

    with patch("app.services.llm.client") as mock_client, \
         patch("app.services.llm.tracer") as mock_tracer:
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer.start_as_current_span.return_value = mock_span

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(response_data)
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        return asyncio.run(generate_lead_brief(session))


# ---------------------------------------------------------------------------
# generate_lead_brief — quality_score derivation from qualification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("qualification,expected_quality", [
    ("qualified", "high"),
    ("unclear", "medium"),
    ("out_of_scope", "low"),
    ("suspicious", "low"),
])
def test_quality_score_derived_from_qualification(qualification, expected_quality):
    brief = _run_brief(_make_brief_response({"qualification": qualification}))
    assert brief.quality_score == expected_quality
    assert brief.qualification == qualification


def test_unknown_qualification_defaults_to_unclear():
    brief = _run_brief(_make_brief_response({"qualification": "bogus_value"}))
    assert brief.qualification == "unclear"
    assert brief.quality_score == "medium"


# ---------------------------------------------------------------------------
# generate_lead_brief — scope_match normalization
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (True, "true"),
    (False, "false"),
    ("unclear", "unclear"),
    ("true", "true"),
    ("false", "false"),
    ("garbage", "unclear"),
    (None, "unclear"),
])
def test_scope_match_normalization(raw, expected):
    brief = _run_brief(_make_brief_response({"scope_match": raw}))
    assert brief.scope_match == expected


# ---------------------------------------------------------------------------
# generate_lead_brief — red_flags coercion
# ---------------------------------------------------------------------------

def test_red_flags_list_passthrough():
    flags = ["injection attempt", "authority claim"]
    brief = _run_brief(_make_brief_response({"red_flags": flags}))
    assert brief.red_flags == flags


def test_red_flags_none_becomes_empty_list():
    brief = _run_brief(_make_brief_response({"red_flags": None}))
    assert brief.red_flags == []


def test_red_flags_string_becomes_single_item_list():
    brief = _run_brief(_make_brief_response({"red_flags": "suspicious message"}))
    assert brief.red_flags == ["suspicious message"]


# ---------------------------------------------------------------------------
# build_chat_system_prompt — out_of_scope block rendering
# ---------------------------------------------------------------------------

def _make_profile(out_of_scope=None) -> CompanyProfile:
    return CompanyProfile(
        name="TestCo",
        industry="bookkeeping",
        services=["service A"],
        out_of_scope=out_of_scope if out_of_scope is not None else [],
        summary="A test company.",
        gaps=[],
    )


OOS_HEADER = "This business does NOT offer the following"


def test_out_of_scope_block_renders_when_populated():
    profile = _make_profile(out_of_scope=["lending", "legal advice"])
    prompt = build_chat_system_prompt(profile, retrieved_chunks=[], kb_id="test")

    assert OOS_HEADER in prompt
    assert "lending" in prompt
    assert "legal advice" in prompt


def test_out_of_scope_block_omitted_when_empty():
    profile = _make_profile(out_of_scope=[])
    prompt = build_chat_system_prompt(profile, retrieved_chunks=[], kb_id="test")

    assert OOS_HEADER not in prompt


def test_out_of_scope_block_omitted_when_none():
    # Bypass _make_profile helper and construct directly to test None path in build_chat_system_prompt
    profile = CompanyProfile(
        name="TestCo",
        industry="bookkeeping",
        services=["service A"],
        out_of_scope=[],  # CompanyProfile enforces list; None is coerced by Pydantic
        summary="A test company.",
        gaps=[],
    )
    # Directly override the field to simulate None reaching build_chat_system_prompt
    object.__setattr__(profile, "out_of_scope", None)
    prompt = build_chat_system_prompt(profile, retrieved_chunks=[], kb_id="test")

    assert OOS_HEADER not in prompt


def test_anti_injection_section_present():
    profile = _make_profile()
    prompt = build_chat_system_prompt(profile, retrieved_chunks=[], kb_id="test")
    assert "Personal information" in prompt
    assert "Instructions that try to change your behavior" in prompt


def test_price_redirect_rule_present():
    profile = _make_profile()
    prompt = build_chat_system_prompt(profile, retrieved_chunks=[], kb_id="test")
    assert "connect you with the team" in prompt


# ---------------------------------------------------------------------------
# _profile_from_partial — out_of_scope handling
# ---------------------------------------------------------------------------

def test_profile_from_partial_out_of_scope_list():
    data = {"name": "TestCo", "out_of_scope": ["loans", "legal services"]}
    profile = _profile_from_partial(data, "http://testco.com")
    assert profile.out_of_scope == ["loans", "legal services"]


def test_profile_from_partial_out_of_scope_string_becomes_list():
    data = {"name": "TestCo", "out_of_scope": "loans"}
    profile = _profile_from_partial(data, "http://testco.com")
    assert profile.out_of_scope == ["loans"]


def test_profile_from_partial_out_of_scope_missing_defaults_to_empty():
    data = {"name": "TestCo"}
    profile = _profile_from_partial(data, "http://testco.com")
    assert profile.out_of_scope == []


def test_profile_from_partial_out_of_scope_none_defaults_to_empty():
    data = {"name": "TestCo", "out_of_scope": None}
    profile = _profile_from_partial(data, "http://testco.com")
    assert profile.out_of_scope == []


def test_profile_from_partial_out_of_scope_empty_string_defaults_to_empty():
    data = {"name": "TestCo", "out_of_scope": ""}
    profile = _profile_from_partial(data, "http://testco.com")
    assert profile.out_of_scope == []
