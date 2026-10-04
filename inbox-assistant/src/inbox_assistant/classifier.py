"""Sorts an email into a category and detects its language.

`parse_classification` is the single gate every classifier's output goes through: anything that
isn't valid JSON matching the schema becomes `needs_human`. The real Anthropic-backed classifier
arrives in Milestone 3; until then `StubClassifier` uses simple keyword rules.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from pydantic import ValidationError

from inbox_assistant.models import Classification, ClassifierResult, IncomingEmail, Usage


class Classifier(Protocol):
    def classify(self, email: IncomingEmail) -> ClassifierResult: ...


def _fallback(reason: str) -> Classification:
    return Classification(
        category="other", language="en", confidence=0.0, needs_human=True, reason=reason
    )


def parse_classification(raw: str) -> tuple[Classification, bool]:
    """Validate raw model output. Returns (classification, fell_back)."""
    text = raw.strip()
    # Tolerate a ```json fence or a sentence around the object, but nothing else.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return _fallback("classifier returned no JSON"), True
    try:
        data = json.loads(match.group(0))
        classification = Classification.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        return _fallback(f"invalid classifier output ({type(exc).__name__})"), True
    # Keep only the primary language tag: "en-US" -> "en".
    language = re.split(r"[-_]", classification.language.strip().lower())[0]
    return classification.model_copy(update={"language": language}), False


# --------------------------------------------------------------------------- stub (Milestone 1)

_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    # Order matters: the first matching category wins.
    ("spam", ("crypto", "bitcoin", "seo services", "you are a winner", "viagra")),
    (
        "complaint",
        (
            "complaint",
            "disappointed",
            "refund",
            "dirty",
            "valitus",
            "pettynyt",
            "likainen",
            "klagomål",
            "besviken",
        ),
    ),
    (
        "quote_request",
        (
            "quote",
            "how much",
            "price for",
            "tarjous",
            "paljonko",
            "hinta",
            "offert",
            "vad kostar",
            "angebot",
            "was kostet",
        ),
    ),
    ("booking", ("book ", "booking", "reserve", "varata", "varaus", "boka", "bokning", "buchen")),
]

_LANGUAGE_WORDS: dict[str, tuple[str, ...]] = {
    "fi": (
        "hei",
        "kiitos",
        "onko",
        "olisiko",
        "mökki",
        "mökin",
        "terveisin",
        "voisitteko",
        "haluaisimme",
        "meitä",
    ),
    "sv": ("hej", "tack", "och", "är", "stugan", "vi", "med vänliga"),
    "de": ("hallo", "danke", "und", "ist", "wir", "ihr", "grüße", "können"),
    "en": ("hello", "hi", "thanks", "the", "and", "is", "we", "regards", "could"),
}


def _guess_language(text: str) -> str:
    words = re.findall(r"[a-zåäöüß]+", text.lower())
    scores = {lang: sum(words.count(w) for w in cues) for lang, cues in _LANGUAGE_WORDS.items()}
    best = max(scores, key=lambda lang: scores[lang])
    return best if scores[best] > 0 else "en"


class StubClassifier:
    """Keyword-based stand-in for the AI classifier. Produces JSON so it exercises the same
    validation path the real model output will."""

    model = "stub-classifier"

    def raw_output(self, email: IncomingEmail) -> str:
        text = f"{email.subject}\n{email.body_text}".lower()
        category, confidence = "other", 0.5
        for name, keywords in _CATEGORY_KEYWORDS:
            if any(k in text for k in keywords):
                category, confidence = name, 0.85
                break
        else:
            if "?" in text:
                category, confidence = "faq", 0.8
        return json.dumps(
            {
                "category": category,
                "language": _guess_language(text),
                "confidence": confidence,
                "needs_human": False,
                "reason": "stub keyword rules",
            }
        )

    def classify(self, email: IncomingEmail) -> ClassifierResult:
        classification, fallback = parse_classification(self.raw_output(email))
        return ClassifierResult(classification, Usage(self.model), fallback)
