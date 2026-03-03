from __future__ import annotations

from typing import Any


FINANCIAL_BLOCK_TERMS = [
    "kredi kart",
    "kart numara",
    "cvv",
    "son kullanma",
    "iban",
    "havale",
    "eft",
    "odeme yap",
    "odeme al",
    "satin al",
    "siparis ver",
    "checkout",
    "credit card",
    "card number",
    "payment",
    "purchase",
    "buy now",
    "wire transfer",
    "bank transfer",
]


def contains_forbidden_financial_intent(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(term in t for term in FINANCIAL_BLOCK_TERMS)


def is_forbidden_tool_payload(payload: Any) -> bool:
    return contains_forbidden_financial_intent(str(payload))

