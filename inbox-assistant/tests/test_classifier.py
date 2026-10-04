from __future__ import annotations

import json

import pytest

from conftest import load_fixture
from inbox_assistant.classifier import StubClassifier, parse_classification

VALID = {
    "category": "faq",
    "language": "fi",
    "confidence": 0.9,
    "needs_human": False,
    "reason": "x",
}


def test_valid_json():
    cls, fallback = parse_classification(json.dumps(VALID))
    assert not fallback
    assert cls.category == "faq" and cls.language == "fi" and cls.confidence == 0.9


def test_code_fence_is_tolerated():
    cls, fallback = parse_classification("```json\n" + json.dumps(VALID) + "\n```")
    assert not fallback and cls.category == "faq"


def test_language_region_is_dropped():
    cls, _ = parse_classification(json.dumps({**VALID, "language": "en-US"}))
    assert cls.language == "en"


@pytest.mark.parametrize(
    "raw",
    [
        "I think this is a FAQ.",
        "{not json}",
        json.dumps({**VALID, "category": "invoice"}),
        json.dumps({**VALID, "confidence": 1.5}),
        json.dumps({k: v for k, v in VALID.items() if k != "needs_human"}),
        "",
    ],
)
def test_bad_output_falls_back_to_needs_human(raw):
    cls, fallback = parse_classification(raw)
    assert fallback
    assert cls.needs_human is True
    assert cls.confidence == 0.0


@pytest.mark.parametrize(
    "fixture, category, language",
    [
        ("01_faq_en.eml", "faq", "en"),
        ("02_quote_request_fi.eml", "quote_request", "fi"),
        ("03_booking_sv.eml", "booking", "sv"),
        ("04_complaint_en.eml", "complaint", "en"),
        ("05_question_de.eml", "faq", "de"),
        ("09_spam.eml", "spam", "en"),
    ],
)
def test_stub_classifier_on_fixtures(fixture, category, language):
    result = StubClassifier().classify(load_fixture(fixture))
    assert result.classification.category == category
    assert result.classification.language == language
    assert not result.fallback
